# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import pytz
import hashlib
from datetime import datetime, timedelta

class HrEmployeeAttendance(models.Model):
    _inherit = 'hr.attendance'

    attendance_type = fields.Selection([('biometric', 'Biometric Device'), ('file', 'File')], default='file')


class HrZkDevice(models.Model):
    _name = 'hr.zk.device.log'
    _description = 'hr.zk.device.log'
    _rec_name = 'host'
    _order = 'check_date DESC, employee_id'

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if 'device_user_id' in fields:
            fields.remove('device_user_id')
        res = super(HrZkDevice, self).read_group(domain, fields, groupby, offset=offset, limit=limit,
                                                 orderby=orderby, lazy=lazy)
        return res

    host = fields.Char('Host (IP)')
    device_user_id = fields.Integer(string="PIN")
    key = fields.Char()
    employee_id = fields.Many2one('hr.employee', compute='_compute_employee_id', store=True)
    check_date = fields.Datetime(string='Check Date')
    check_day = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ], 'Day', compute="_compute_day", store=True)
    status = fields.Selection([('exportable', 'Exportable'),
                               ('duplicated', 'Duplicated'),
                               ('incidence', 'On Incidence')], compute="_compute_status", store=True)
    state = fields.Selection([('original', 'Original'),
                              ('modified', 'Modified'),
                              ('manual', 'Manual')], default='original')
    phase = fields.Selection([('draft', 'Draft'),
                              ('approved', 'Approved')], default='draft')
    period_id = fields.Many2one('payment.period', compute='_compute_period',
                                string='Period', store=True, ondelete='restrict')
    block_id = fields.Many2one('hr.zk.device.block')

    def write(self, vals):
        if 'check_date' in vals:
            vals['state'] = 'modified'
        return super(HrZkDevice, self).write(vals)

    @api.depends('device_user_id')
    def _compute_employee_id(self):
        for r in self:
            r.employee_id = self.env['hr.employee'].search([('pin', '=', r.device_user_id)], limit=1).id

    @api.depends('check_date')
    def _compute_day(self):
        for r in self:
            r.check_day = str(self.get_tz_datetime(r.check_date, self.env.user).weekday())

    @api.depends('employee_id', 'check_date')
    def _compute_status(self):

        date_now = datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        for r in self:
            frame = (r.check_date - timedelta(minutes=5)).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            duplicated_id = self.search([('employee_id', '=', r.employee_id.id),
                                         ('check_date', '>=', frame),
                                         ('check_date', '<', r.check_date)])
            r.status = 'duplicated' if duplicated_id else 'exportable'
            incidence_id = self.env['attendance.incidence'].search([('employee_id', '=', r.employee_id.id),
                                                                    ('check_in', '<=', date_now),
                                                                    ('check_out', '>=', date_now),
                                                                    ('state', '=', 'approved')])
            r.status = 'incidence' if incidence_id else r.status

    @api.depends('employee_id', 'check_date')
    def _compute_period(self):
        for _id in self:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', _id.employee_id.id)], limit=1)
            if contract_id:
                period_group_id = contract_id.period_group_id.id
                tz_end = self.get_tz_datetime(_id.check_date, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                period_id = self.env['payment.period'].search([('group_id', '=', period_group_id),
                                                               ('to_date', '>=', tz_end),
                                                               ('from_date', '<=', tz_end)])
                if period_id:
                    _id.period_id = period_id.id

    def create_log(self, log):
        for record in log.items():
            if not self.search([('key', '=', record[0])]):
                _id = self.create({'key': record[0], 'host': record[1][0], 'device_user_id': record[1][1],
                                   'check_date': self.remove_tz_datetime(record[1][2], self.env.user)})
                if _id.status in ['duplicated', 'incidence']:
                    _id.phase = 'approved'
        self.create_block()
        return True

    def remove_tz_datetime(self, check_date, user_id):
        check_date = datetime.strptime(check_date, DEFAULT_SERVER_DATETIME_FORMAT)
        Params = self.env['ir.config_parameter']
        tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
        tz = Params.get_param('tz') if tz_param else user_id.tz
        return pytz.timezone(tz).localize(check_date.replace(tzinfo=None), is_dst=False).astimezone(
            pytz.UTC).replace(tzinfo=None)

    def get_tz_datetime(self, _datetime, user_id):
        Params = self.env['ir.config_parameter']
        tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
        tz = Params.get_param('tz') if tz_param else None
        if tz:
            tz_datetime = _datetime.astimezone(pytz.timezone(str(tz)))
        else:
            user_id = user_id if user_id else self.env.user
            tz_datetime = _datetime.astimezone(pytz.timezone(str(user_id.tz)))
        return tz_datetime

    def create_block(self, day=datetime.now(), employee_ids=None, current_day=True):
        tz_date = self.get_tz_datetime(day, self.env.user)
        day_end = tz_date.replace(hour=23, minute=59, second=59, microsecond=0).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        day_start = tz_date.replace(hour=0, minute=0, second=0, microsecond=1).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        utc_date_end = self.remove_tz_datetime(day_end, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        utc_date_start = self.remove_tz_datetime(day_start, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        check_ids = self.search([('status', '=', 'exportable'), ('employee_id', '!=', None), ('block_id', '=', None),
                                 ('check_date', '>=', utc_date_start),
                                 ('check_date', '<=', utc_date_end)])

        employee_ids = list(set([employee_id.id for employee_id in check_ids.mapped('employee_id')])) if not employee_ids else employee_ids

        for employee_id in employee_ids:
            block_id = self.env['hr.zk.device.block'].search([('employee_id', '=', employee_id),
                                                              ('date_end', '=', None),
                                                              ('date_start', '>=', utc_date_start),
                                                              ('date_start', '<=', utc_date_end)
                                                              ]) if current_day else None

            for check_id in check_ids.filtered(lambda r: r.employee_id.id == employee_id).sorted(key=lambda s: s.check_date):
                if not block_id:
                    block_id = self.env['hr.zk.device.block'].create({'employee_id': check_id.employee_id.id,
                                                                      'date_start': check_id.check_date})
                    check_id.block_id = block_id.id
                else:
                    block_id.write({'date_end': check_id.check_date})
                    check_id.block_id = block_id.id
                    block_id = None
            if not current_day:
                unfinish_block_id = self.env['hr.zk.device.block'].search([('employee_id', '=', employee_id),
                                                                           ('date_end', '=', None),
                                                                           ('date_start', '>=', utc_date_start),
                                                                           ('date_start', '<=', utc_date_end)])
                if unfinish_block_id:
                    contract_id = self.env['hr.contract'].search([('employee_id', '=', employee_id)], limit=1)
                    if contract_id:
                        attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                            .filtered(lambda r: int(r.dayofweek) == tz_date.weekday()).sorted(key=lambda r: r.hour_from,
                                                                                              reverse=True)
                        if attendance_ids:
                            hour = int('{0:02.0f}'.format(*divmod(attendance_ids[0].hour_to * 60, 60)))
                            minutes = int('{1:02.0f}'.format(*divmod(attendance_ids[0].hour_to * 60, 60)))
                            hour_to = tz_date.replace(hour=hour, minute=minutes, second=0)
                            utc_hour_to = self.remove_tz_datetime(hour_to.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                                                  self.env.user)
                            unfinish_block_id.write({'date_end': utc_hour_to})

    def create_attendance(self, day=datetime.now(), employee_ids=None, current_day=True):
        tz_date = self.get_tz_datetime(day, self.env.user)
        day_end = tz_date.replace(hour=23, minute=59, second=59, microsecond=0).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        day_start = tz_date.replace(hour=0, minute=0, second=0, microsecond=1).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        utc_date_end = self.remove_tz_datetime(day_end, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        utc_date_start = self.remove_tz_datetime(day_start, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        block_ids = self.env['hr.zk.device.block'].search([('employee_id', '!=', None),
                                                           ('date_start', '>=', utc_date_start),
                                                           ('date_start', '<=', utc_date_end)])
        employee_ids = list(set([employee_id.id for employee_id in block_ids.mapped('employee_id')])) if not employee_ids else employee_ids

        for employee_id in employee_ids:
            for block_id in block_ids.filtered(lambda r: r.employee_id.id == employee_id).sorted(key=lambda s: s.date_start):
                check_in_overlap = self.env['hr.attendance'].search([('employee_id', '=', employee_id),
                                                                     ('check_in', '>', block_id.date_start),
                                                                     ('check_in', '<', block_id.date_end)])
                check_out_overlap = self.env['hr.attendance'].search([('employee_id', '=', employee_id),
                                                                      ('check_out', '>', block_id.date_start),
                                                                      ('check_out', '<', block_id.date_end)])
                if not check_in_overlap and not check_out_overlap and block_id.date_end:
                    self.env['hr.attendance'].create(
                            {'employee_id': employee_id,
                             'check_in': block_id.date_start,
                             'check_out': block_id.date_end,
                             'attendance_type': 'biometric'})

    def create_missing_log(self, day=datetime.now(), employee_ids=None):
        tz_date = self.get_tz_datetime(day, self.env.user)
        day_end = tz_date.replace(hour=23, minute=59, second=59, microsecond=0).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        day_start = tz_date.replace(hour=0, minute=0, second=0, microsecond=1).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        utc_date_end = self.remove_tz_datetime(day_end, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        utc_date_start = self.remove_tz_datetime(day_start, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        log_ids = self.search([('employee_id', '!=', None),
                               ('check_date', '>=', utc_date_start),
                               ('check_date', '<=', utc_date_end),
                               ('status', '=', 'exportable')])
        employee_ids = list(set([employee_id.id for employee_id in log_ids.mapped('employee_id')])) if not employee_ids else employee_ids

        for employee_id in employee_ids:
            employee_checks = len(log_ids.filtered(lambda r: r.employee_id.id == employee_id))
            if employee_checks % 2 != 0:
                # Get checks needed by calendar
                contract_id = self.env['hr.contract'].search([('employee_id', '=', employee_id),
                                                              ('state', 'in', ['open', 'pending'])], limit=1)
                if contract_id:
                    attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                        .filtered(lambda r: int(r.dayofweek) == int(tz_date.weekday()))
                    calendar_checks = []
                    for attendance_id in attendance_ids:
                        to_hour = int('{0:02.0f}'.format(*divmod(attendance_id.hour_to * 60, 60)))
                        to_minutes = int('{1:02.0f}'.format(*divmod(attendance_id.hour_to * 60, 60)))
                        from_hour = int('{0:02.0f}'.format(*divmod(attendance_id.hour_from * 60, 60)))
                        from_minutes = int('{1:02.0f}'.format(*divmod(attendance_id.hour_from * 60, 60)))
                        calendar_checks.append(tz_date.replace(hour=to_hour, minute=to_minutes, second=0))
                        calendar_checks.append(tz_date.replace(hour=from_hour, minute=from_minutes, second=0))
                    if employee_checks < len(calendar_checks):
                        for log_id in log_ids.filtered(lambda r: r.employee_id.id == employee_id).sorted(key=lambda s: s.check_date):
                            index = 0
                            differences = []
                            for cal_check in calendar_checks:
                                check_date = self.get_tz_datetime(log_id.check_date, self.env.user)
                                differences.append((index, abs(cal_check - check_date).total_seconds()))
                                index = index + 1
                            differences.sort(key=lambda x: x[1])
                            if differences:
                                calendar_checks.pop(differences[0][0])
                        for cal_check in calendar_checks:
                            _employee_id = self.env['hr.employee'].browse([employee_id])
                            key = hashlib.new('sha1', bytes('{}.{}'.format(datetime.timestamp(cal_check),
                                                                           _employee_id.pin).encode())).hexdigest()
                            self.create({'key': key, 'host': None, 'device_user_id': _employee_id.pin,
                                         'check_date': self.remove_tz_datetime(cal_check.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                                                          self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                         'state': 'manual'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def approve_log_btn(self, context=None):
        context = context or {}
        if context.get('active_ids'):
            self.browse(context.get('active_ids')).write({'phase': 'approved'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open(self):
        tree_view_id = self.env.ref('aci_estimation.hr_zk_device_tree_view').id
        wanted_date = datetime.combine(self.check_date, datetime.min.time())
        day_start = wanted_date.replace(hour=0, minute=0, second=0, microsecond=1).strftime(
            DEFAULT_SERVER_DATETIME_FORMAT)
        day_end = wanted_date.replace(hour=23, minute=59, second=59, microsecond=0).strftime(
            DEFAULT_SERVER_DATETIME_FORMAT)
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree')],
            'view_mode': 'tree',
            'name': '{} Logs'.format(self.employee_id.name),
            'res_model': 'hr.zk.device.log',
            'context': {'employee_id': self.employee_id.id},
            'domain': [('employee_id', '=', self.employee_id.id),
                       ('check_date', '>=', self.env['hr.zk.device.log'].remove_tz_datetime(day_start, self.env.user)),
                       ('check_date', '<=', self.env['hr.zk.device.log'].remove_tz_datetime(day_end, self.env.user))],
        }
        return action


class HrZkDeviceBlock(models.Model):
    _name = 'hr.zk.device.block'
    _description = 'hr.zk.device.block'
    _order = 'date_start DESC'

    employee_id = fields.Many2one('hr.employee')
    date_start = fields.Datetime()
    date_end = fields.Datetime()
    period_id = fields.Many2one('payment.period', compute='_compute_period',
                                string='Period', store=True, ondelete='restrict')
    duration = fields.Float('Duration (hrs)', compute='_compute_duration', store=True)
    scheduled_hours = fields.Float('Scheduled Hours', compute='_compute_scheduled_hours', store=True)

    @api.depends('employee_id', 'date_start')
    def _compute_period(self):
        for _id in self:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', _id.employee_id.id)], limit=1)
            if contract_id:
                period_group_id = contract_id.period_group_id.id
                tz_end = self.env['hr.zk.device.log'].get_tz_datetime(_id.date_start, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                period_id = self.env['payment.period'].search([('group_id', '=', period_group_id),
                                                               ('to_date', '>=', tz_end),
                                                               ('from_date', '<=', tz_end)])
                if period_id:
                    _id.period_id = period_id.id

    @api.depends('date_end', 'date_start')
    def _compute_duration(self):
        for blocktime in self:
            if blocktime.date_end:
                diff = fields.Datetime.from_string(blocktime.date_end) - fields.Datetime.from_string(
                    blocktime.date_start)
                blocktime.duration = round(diff.total_seconds() / 3600.0, 2)
            else:
                blocktime.duration = 0.0

    @api.depends('employee_id', 'period_id')
    def _compute_scheduled_hours(self):
        Log = self.env['hr.zk.device.log']
        for r in self:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', r.employee_id.id),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            if contract_id:
                utc_date_from = datetime.strptime('{} 12:00:00'.format(r.period_id.from_date), DEFAULT_SERVER_DATETIME_FORMAT)
                date_from = Log.get_tz_datetime(utc_date_from, self.env.user)

                utc_date_to = datetime.strptime('{} 12:00:00'.format(r.period_id.to_date), DEFAULT_SERVER_DATETIME_FORMAT)
                date_to = Log.get_tz_datetime(utc_date_to, self.env.user)
                scheduled_hours = 0
                while date_from.strftime('%Y-%m-%d') <= date_to.strftime('%Y-%m-%d'):
                    attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                        .filtered(lambda a: int(a.dayofweek) == date_from.weekday())
                    for attendance_id in attendance_ids:
                        from_hour = int('{0:02.0f}'.format(*divmod(attendance_id.hour_from * 60, 60)))
                        from_minutes = int('{1:02.0f}'.format(*divmod(attendance_id.hour_from * 60, 60)))
                        to_hour = int('{0:02.0f}'.format(*divmod(attendance_id.hour_to * 60, 60)))
                        to_minutes = int('{1:02.0f}'.format(*divmod(attendance_id.hour_to * 60, 60)))
                        start = date_from.replace(hour=from_hour, minute=from_minutes, second=0)
                        end = date_from.replace(hour=to_hour, minute=to_minutes, second=0)
                        scheduled_hours = scheduled_hours + (end - start).total_seconds() / 3600
                    date_from = date_from + timedelta(days=1)
                r.scheduled_hours = scheduled_hours


class HrZkDeviceIncidence(models.Model):
    _name = 'hr.zk.device.incidence'
    _description = 'hr.zk.device.incidence'
    _auto = False
    _order = 'check_date DESC'

    employee_id = fields.Many2one('hr.employee')
    check_date = fields.Datetime()
    check_day = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')], 'Day')
    period_id = fields.Many2one('payment.period', string='Period', ondelete='restrict')
    period_from = fields.Date()
    period_to = fields.Date()
    scheduled_check = fields.Integer()
    done_check = fields.Integer(string='Checks')
    manual_check = fields.Integer(string='Manual Check')
    diff_check = fields.Integer()

    @api.model
    def init(self):
        cr = self.env.cr
        tools.sql.drop_view_if_exists(cr, 'hr_zk_device_incidence')
        cr.execute("""
                        CREATE OR REPLACE VIEW hr_zk_device_incidence AS
                      WITH done_check AS (SELECT l.employee_id, l.check_day, l.period_id, per.from_date, per.to_date, 
                        to_char(l.check_date at time zone 'utc' at time zone 'mexico/general', 'YYYY-MM-DD') as r_check_date, 
                        count(l.check_date)::INTEGER as done_check 
                        FROM hr_zk_device_log l
                        INNER JOIN payment_period per ON per.id = l.period_id
                        WHERE employee_id IS NOT NULL and status = 'exportable' 
                        GROUP BY period_id, employee_id, check_day, r_check_date, from_date, to_date ORDER BY r_check_date DESC, employee_id),
                        
                        scheduled_check AS (SELECT c.employee_id, c.resource_calendar_id, cal.dayofweek, count(cal.id)*2 as scheduled_check FROM hr_contract c 
                        JOIN resource_calendar_attendance cal on cal.calendar_id = c.resource_calendar_id 
                        WHERE c.state in ('open', 'pending') and employee_id IS NOT NULL
                        GROUP BY employee_id, resource_calendar_id, dayofweek
                        ORDER BY c.employee_id DESC, cal.dayofweek),
                        
                        manual_check AS (SELECT l.employee_id, 
                        to_char(l.check_date at time zone 'utc' at time zone 'mexico/general', 'YYYY-MM-DD') as r_check_date, 
                        count(l.check_date)::INTEGER as manual_check 
                        FROM hr_zk_device_log l
                        WHERE employee_id IS NOT NULL and status = 'exportable' AND state = 'manual' 
                        GROUP BY period_id, employee_id, r_check_date)
                        
                        SELECT ROW_NUMBER() OVER(ORDER BY dc.employee_id, dc.period_id, dc.r_check_date) AS id,
                        dc.employee_id, dc.check_day, dc.period_id, dc.from_date as period_from, dc.to_date as period_to,
                        dc.r_check_date::TIMESTAMP at time zone 'mexico/general' at time zone 'utc' as check_date, 
                        sc.scheduled_check::INTEGER, dc.done_check, (sc.scheduled_check - dc.done_check)::INTEGER as diff_check,
                        COALESCE(mc.manual_check, 0) as manual_check
                        FROM done_check dc
                        JOIN scheduled_check sc ON sc.employee_id = dc.employee_id AND dc.check_day = sc.dayofweek
                        LEFT JOIN manual_check mc ON mc.employee_id = dc.employee_id AND mc.r_check_date like dc.r_check_date
                        WHERE (sc.scheduled_check - dc.done_check) != 0 OR mc.manual_check > 0
                        """)

    def action_open(self):
        tree_view_id = self.env.ref('aci_estimation.hr_zk_device_tree_view').id
        wanted_date = datetime.combine(self.check_date, datetime.min.time())
        day_start = wanted_date.replace(hour=0, minute=0, second=0, microsecond=1).strftime(
            DEFAULT_SERVER_DATETIME_FORMAT)
        day_end = wanted_date.replace(hour=23, minute=59, second=59, microsecond=0).strftime(
            DEFAULT_SERVER_DATETIME_FORMAT)
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree')],
            'view_mode': 'tree',
            'name': '{} Logs'.format(self.employee_id.name),
            'res_model': 'hr.zk.device.log',
            'context': {'employee_id': self.employee_id.id},
            'domain': [('employee_id', '=', self.employee_id.id),
                       ('check_date', '>=', self.env['hr.zk.device.log'].remove_tz_datetime(day_start, self.env.user)),
                       ('check_date', '<=', self.env['hr.zk.device.log'].remove_tz_datetime(day_end, self.env.user))],
        }
        return action


class HrZkDeviceHours(models.Model):
    _name = 'hr.zk.device.hours'
    _description = 'hr.zk.device.hours'
    _auto = False
    _order = 'period_id DESC, employee_id'

    employee_id = fields.Many2one('hr.employee')
    resource_calendar_id = fields.Many2one('resource.calendar', 'Work Schedule')
    period_id = fields.Many2one('payment.period', string='Period', ondelete='restrict')
    from_date = fields.Datetime()
    to_date = fields.Datetime()
    scheduled_hours = fields.Float(string='Scheduled Hours')
    worked_hours = fields.Float(string='Worked Hours')
    diff_hours = fields.Float()

    @api.model
    def init(self):
        cr = self.env.cr
        cr.execute("""
                CREATE OR REPLACE VIEW hr_zk_device_hours AS
              SELECT ROW_NUMBER() OVER(ORDER BY b.employee_id, b.period_id, c.resource_calendar_id) AS id,
              b.employee_id, c.resource_calendar_id, b.period_id, per.from_date, per.to_date, sum(b.scheduled_hours) / count(b.id) as scheduled_hours, sum(b.duration) as worked_hours,
                (sum(b.scheduled_hours) / count(b.id)) - sum(b.duration) as diff_hours
            FROM hr_zk_device_block b
            INNER JOIN payment_period per ON per.id = b.period_id
            INNER JOIN hr_contract c ON c.employee_id = b.employee_id AND c.state = 'open'
            GROUP BY period_id, b.employee_id, c.resource_calendar_id, from_date, to_date ORDER BY period_id DESC, employee_id
                """)

    def action_open(self):
        tree_view_id = self.env.ref('aci_estimation.hr_zk_device_block_tree_view').id
        pivot_view_id = self.env.ref('aci_estimation.hr_zk_device_block_pivot_view').id
        timeline_view_id = self.env.ref('aci_estimation.hr_zk_device_block_timeline_view').id
        action = {
            'type': 'ir.actions.act_window',
            'views': [(pivot_view_id, 'pivot'), (tree_view_id, 'tree'), (timeline_view_id, 'timeline')],
            'view_mode': 'pivot,timeline,tree',
            'name': '{} Blocks'.format(self.employee_id.name),
            'res_model': 'hr.zk.device.block',
            'context': {'employee_id': self.employee_id.id},
            'domain': [('employee_id', '=', self.employee_id.id),
                       ('period_id', '=', self.period_id.id)],
        }
        return action

    def action_open_log(self):
        tree_view_id = self.env.ref('aci_estimation.hr_zk_device_tree_view').id
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree')],
            'view_mode': 'tree',
            'name': '{} Logs'.format(self.employee_id.name),
            'res_model': 'hr.zk.device.log',
            'context': {'employee_id': self.employee_id.id},
            'domain': [('employee_id', '=', self.employee_id.id),
                       ('period_id', '=', self.period_id.id)],
        }
        return action

class HrZkDeviceReport(models.Model):
    _name = 'hr.zk.device.report'
    _description = 'hr.zk.device.report'
    _auto = False
    _order = 'period_id DESC, employee_id'

    period_id = fields.Many2one('payment.period', string='Period', ondelete='restrict')
    period_from = fields.Datetime()
    period_to = fields.Datetime()
    employee_id = fields.Many2one('hr.employee')
    start_date = fields.Datetime()
    end_date = fields.Datetime()
    block_type = fields.Selection([('tracking_step', 'Tracking Step'),
                                   ('tracking_wo', 'Tracking WorkOrder'),
                                   ('incidence', 'Incidence'),
                                   ('productivity_block', 'Activity Block'),
                                   ('attendance_block', 'Attendance Block')])
    state = fields.Selection([('active', 'Active'), ('inactive', 'Inactive')])
    block_origin = fields.Selection([('delay', 'Delay'),
                                     ('calendar', 'Calendar'),
                                     ('incidence', 'Incidence'),
                                     ('payable', 'Payable Incidence'),
                                     ('timeoff', 'Calendar TimeOff'),
                                     ('extra', 'After Hours')
                                     ])

    @api.model
    def init(self):
        cr = self.env.cr
        cr.execute("""
                CREATE OR REPLACE VIEW hr_zk_device_report AS
                WITH employee_ids AS (SELECT DISTINCT employee_id FROM hr_zk_device_log WHERE employee_id IS NOT NULL
                UNION 
                SELECT DISTINCT employee_id FROM hr_productivity_block),
                
                productivity_block as (SELECT pb.period_id, per.from_date as period_from, per.to_date as period_to, e.employee_id, pb.start_date as start_date, pb.end_date as end_date, 'productivity_block' as block_type, pb.block_type as state, pb.block_origin as block_origin
                FROM employee_ids e
                JOIN hr_productivity_block pb ON pb.employee_id = e.employee_id
                JOIN payment_period per ON per.id = pb.period_id),
                
                tracking_step as (SELECT pro.period_id, per.from_date as period_from, per.to_date as period_to, e.employee_id, pro.final_start_date as start_date, pro.final_end_date as end_date, 'tracking_step' as block_type, NULL as state, NULL as block_origin
                FROM employee_ids e
                JOIN mrp_workcenter wc ON wc.employee_id = e.employee_id 
                JOIN mrp_workcenter_productivity pro ON pro.resource_id = wc.id
                JOIN payment_period per ON per.id = pro.period_id
                WHERE pro.tracking_origin = 'step' and pro.step_id IS NOT NULL),
                
                tracking_wo as (SELECT pro.period_id, per.from_date as period_from, per.to_date as period_to, e.employee_id, pro.final_start_date as start_date, pro.final_end_date as end_date, 'tracking_wo' as block_type, NULL as state, NULL as block_origin
                FROM employee_ids e
                JOIN mrp_workcenter wc ON wc.employee_id = e.employee_id 
                JOIN mrp_workcenter_productivity pro ON pro.resource_id = wc.id
                JOIN payment_period per ON per.id = pro.period_id
                WHERE pro.tracking_origin = 'workorder'),
                
                attendance_block as (SELECT blo.period_id,per.from_date as period_from, per.to_date as period_to,  e.employee_id, blo.date_start as start_date, blo.date_end as end_date, 'attendance_block' as block_type, NULL as state, NULL as block_origin
                FROM employee_ids e
                JOIN hr_zk_device_block blo ON blo.employee_id = e.employee_id
                JOIN payment_period per ON per.id = blo.period_id),
                
                incidence as (SELECT inc.period_id,per.from_date as period_from, per.to_date as period_to,  e.employee_id, inc.check_in as start_date, inc.check_out as end_date, 'incidence' as block_type, NULL as state, NULL as block_origin
                FROM employee_ids e
                JOIN attendance_incidence inc ON inc.employee_id = e.employee_id
                JOIN payment_period per ON per.id = inc.period_id
                WHERE inc.state = 'approved'),
                
                report as (SELECT * FROM productivity_block
                UNION
                SELECT * FROM tracking_step
                UNION
                SELECT * FROM tracking_wo
                UNION
                SELECT * FROM attendance_block
                UNION
                SELECT * FROM incidence)
                
                SELECT ROW_NUMBER() OVER(ORDER BY employee_id, period_id, block_type) AS id,
                period_id, employee_id, start_date, end_date, block_type, state, block_origin, period_from, period_to
                FROM report
    """)


