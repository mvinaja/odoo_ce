# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from copy import deepcopy
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

from . import general_tools


class AttendanceIncidence(models.Model):
    _name = 'attendance.incidence'
    _description = 'attendance.incidence'
    _order = 'period_id, employee_id, check_in'

    employee_id = fields.Many2one('hr.employee', 'Employee')
    name = fields.Char('Description')
    type_incidence = fields.Selection([
        ('leave', 'Leave Not Payable'),
        ('work_not_payable', 'Work Not Payable'),
        ('work_out_schedule', 'Work Out Schedule'),
        ('holiday', 'Holiday by Law'),
        ('holiday_company', 'Holiday by Company'),
        ('paid_holiday', 'Paid Holiday by Law'),
        ('paid_holiday_company', 'Paid Holiday by Company'),
        ('incomplete_logs', 'Incomplete Attendance Logs'),
        ('omission', 'Worker Omission')
    ], 'Type', default='work_out_schedule')
    check_in = fields.Datetime('Start', default=fields.Datetime.now, required=True)
    check_out = fields.Datetime('End')
    missing_log_date = fields.Datetime('Missing Log Date')
    is_computed = fields.Boolean(default=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], default='draft')
    weekday = fields.Integer()

    structure_type_id = fields.Many2one(
        'hr.payroll.structure.type', compute='_compute_structure_type', store=True, string='Salary Structure Type')
    department_id = fields.Many2one('hr.department', string="Department",
        related="employee_id.department_id", readonly=True)
    created_by_user = fields.Boolean('Created By User', compute='_compute_created_by_user')
    date_computed = fields.Date('Date', compute='_compute_date', store=True,
        inverse='inverse_value')
    day_computed = fields.Char('Day', compute='_compute_date', store=True,
        inverse='inverse_value')
    check_in_hour = fields.Float('H.Start', compute='_compute_hours', store=True,
        inverse='inverse_value')
    check_out_hour = fields.Float('H.End', compute='_compute_hours', store=True,
        inverse='inverse_value')
    worked_hours = fields.Float('Hours', compute='_compute_worked_hours', store=True, readonly=True)
    ready_to_approve = fields.Boolean(compute='_compute_ready_to_approve', store=True)
    period_id_computed = fields.Many2one('payment.period', string='Period Com.',
        compute='_compute_period', index=True, ondelete='restrict', search='_search_period', compute_sudo=True)
    period_id = fields.Many2one('payment.period', compute='_compute_period',
        string='Period', store=True, ondelete='restrict', compute_sudo=True)
    qty_real_logs = fields.Integer('Quantity Logs / Day', compute='_compute_qty_real_logs', store=True)
    count = fields.Integer(string='Count', compute='_compute_count', store=True)
    # Used to measure on pivot view
    single_count = fields.Integer('Count', default=1)
    # Blocks functionality
    productivity_block = fields.Boolean(string='Create Block', default=False)
    # Dummy to search
    prev_period = fields.Boolean()

    def write(self, vals):
        if 'check_in' in vals.keys() or 'check_out' in vals.keys():
            self.order_dates(vals)
        return super(AttendanceIncidence, self).write(vals)

    @api.model
    def _read_group_process_groupby(self, gb, query):
        response = super(AttendanceIncidence, self)._read_group_process_groupby(gb, query)
        if self.env.context.get('custom_datetime_format', False):
            split = gb.split(':')
            field_type = self._fields[split[0]].type
            gb_function = split[1] if len(split) == 2 else None
            temporal = field_type in ('date', 'datetime')
            if temporal:
                display_formats = {
                    # 'day': 'dd MMM yyyy', # yyyy = normal year
                    'day': 'dd.MMMM - EEE', # yyyy = normal year
                    'week': "'W'w YYYY",  # w YYYY = ISO week-year
                    'month': 'MMMM yyyy',
                    'quarter': 'QQQ yyyy',
                    'year': 'yyyy',
                }
            response['display_format'] = temporal and display_formats[gb_function or 'month'] or None

        return response

    def _search_period(self, operator, value):
        assert operator == 'in'
        ids = []
        for period in self.env['payment.period'].browse(value):
            self._cr.execute("""
                    SELECT a.id
                        FROM attendance_incidence a
                    WHERE %(date_to)s >= a.date_computed
                        AND %(date_from)s <= a.date_computed
                    GROUP BY a.id""", {'date_from': period.from_date,
                                       'date_to': period.to_date})
            ids.extend([row[0] for row in self._cr.fetchall()])
        return [('id', 'in', ids)]

    def _get_tz_datetime(self, datetime, user_id):
        user_id = user_id if user_id else self.env.user
        tz = str(user_id.tz) if user_id.tz else 'Mexico/General'
        tz_datetime = datetime.astimezone(pytz.timezone(tz))
        return tz_datetime

    def inverse_value(self):
        return 'done'

    @api.depends('employee_id')
    def _compute_structure_type(self):
        Contract = self.env['hr.contract']
        for _id in self:
            contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
            if contract_id:
                _id.structure_type_id = contract_id.structure_type_id.id

    @api.depends('is_computed')
    def _compute_created_by_user(self):
        for _id in self:
            _id.created_by_user = not _id.is_computed

    @api.depends('check_in')
    def _compute_date(self):
        for _id in self:
            checkIn_utc = _id.check_in
            date = self._get_tz_datetime(checkIn_utc, self.env.user)
            _id.date_computed = date.date()
            _id.day_computed = date.strftime('%A')


    @api.depends('check_in', 'check_out')
    def _compute_hours(self):
        for _id in self:
            checkIn_utc = _id.check_in
            date = self._get_tz_datetime(checkIn_utc, self.env.user)
            _id.check_in_hour = general_tools.get_float_from_time(date)
            if _id.check_out:
                checkOut_utc = _id.check_out
                date = self._get_tz_datetime(checkOut_utc, self.env.user)
                _id.check_out_hour = general_tools.get_float_from_time(date)

    @api.depends('check_in', 'check_out')
    def _compute_worked_hours(self):
        for _id in self:
            if _id.check_out:
                delta = _id.check_out - _id.check_in
                _id.worked_hours = delta.total_seconds() / 3600.0

    @api.depends('check_in', 'check_out')
    def _compute_ready_to_approve(self):
        for _id in self:
            if _id.check_in and _id.check_out:
                _id.ready_to_approve = True
            else:
                _id.ready_to_approve = False

    # @api.depends('employee_id', 'check_in', 'check_out', 'period_id_computed.to_date', 'period_id_computed.from_date')
    @api.depends('employee_id', 'check_in', 'check_out', 'date_computed', 'period_id_computed.to_date', 'period_id_computed.from_date')
    def _compute_period(self):
        """Links the incidence to the corresponding period
        """
        Contract = self.env['hr.contract']
        # Calendar = self.env['resource.calendar']
        for _id in self:
            contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
            # check_in = Calendar.get_string_datetime_with_tz(_id.check_in)
            if contract_id:
                for grp in contract_id.period_group_id:
                    corresponding_period = self.env['payment.period'].search(
                        # [('to_date', '>=', check_in), ('from_date', '<=', check_in),
                        [('to_date', '>=', _id.date_computed), ('from_date', '<=', _id.date_computed),
                        ('group_id', '=', grp.period_group_id.id)], limit=1)
                    if corresponding_period:
                        _id.period_id_computed = corresponding_period[0]
                        _id.period_id = corresponding_period[0]

    @api.depends('date_computed', 'employee_id')
    def _compute_qty_real_logs(self):
        AttLog = self.env['attendance.log']
        for _id in self:
            date_computed = _id.date_computed
            employee_id = _id.employee_id
            if date_computed and employee_id:
                _id.qty_real_logs = AttLog.search_count([
                    ('date_computed', '=', date_computed),
                    ('employee_id', '=', employee_id.id),
                    ('discarded', '=', False)
                ])

    @api.depends('date_computed', 'employee_id')
    def _compute_count(self):
        for _id in self:
            _id.count = self.search_count([
                ('date_computed', '=', _id.date_computed),
                ('employee_id', '=', _id.employee_id.id)
            ])

    def approve_incidence_button(self):
        self.ensure_one()
        return self.approve_incidence()

    def reject_incidence_button(self):
        self.ensure_one()
        self.reject_incidence()

    def send_to_draft_button(self):
        self.ensure_one()
        self.send_to_draft_incidence()

    def check_schedule_employee_leaves(self, employee_ids, date=False):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Incidence = self.env['attendance.incidence']
        for employee_id in employee_ids:
            search = [('employee_id', '=', employee_id.id),('period_id', '=', self.period_id.id)]
            if date:
                search.append(('date_computed', '=', date))
            Attendance.search(search).check_schedule_leaves()
            Incidence.search(search).check_schedule_leaves()

    def check_schedule_leaves(self):
        Contract = self.env['hr.contract']
        for _id in self:
            contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
            if not contract_id or not _id.check_out:
                continue
            # calendar_id = _id.employee_id.calendar_id
            calendar_id = contract_id.resource_calendar_id
            if not calendar_id:
                continue

            checkIn_utc = datetime.strptime(_id.check_in, DEFAULT_SERVER_DATETIME_FORMAT)
            check_in = self._get_tz_datetime(checkIn_utc, self.env.user)
            check_in_hour = self.get_float_hour(check_in)

            checkOut_utc = datetime.strptime(_id.check_out, DEFAULT_SERVER_DATETIME_FORMAT)
            check_out = self._get_tz_datetime(checkOut_utc, self.env.user)
            check_out_hour = self.get_float_hour(check_out)
            weekday = check_in.weekday()

            leave_ids = calendar_id.schedule_leave_ids.filtered(lambda r: int(r.dayofweek) == int(weekday))
            unlink = False
            for leave in leave_ids:
                # Leave wraps incidence
                if leave.hour_from <= check_in_hour and leave.hour_to >= check_out_hour:
                    unlink = True
                    break
                # Leave in middle of incidence
                elif leave.hour_from >= check_in_hour and leave.hour_to <= check_out_hour:
                    new_att = _id.process_att_middle_leave(leave.hour_from, leave.hour_to, check_out)
                    if new_att.worked_hours > 0:
                        new_att.check_schedule_leaves()
                    else:
                        new_att.unlink()
                # Leave hour_from in middle of inciedence
                elif leave.hour_from >= check_in_hour and leave.hour_from < check_out_hour:
                    self.process_att_right_leave(leave.hour_from, check_out)
                # Leave hour_to in middle of incidence
                elif leave.hour_to <= check_out_hour and leave.hour_to > check_in_hour:
                    self.process_att_left_leave(leave.hour_to, check_in)

                if _id.worked_hours <= 0:
                    unlink = True
                    break

            if unlink or _id.worked_hours <= 0:
                _id.unlink()

    @api.model
    def generate_date_tz(self, employee_id, date):
        tz = False
        if employee_id:
            tz = employee_id.user_id.partner_id.tz

        att_tz = pytz.timezone(tz or 'utc')

        if not date:
            date = datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        attendance_dt = datetime.strptime(date, DEFAULT_SERVER_DATETIME_FORMAT).replace(tzinfo=att_tz)

        return attendance_dt.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def get_date_str_tz(self, str_date):
        return self.get_date_tz(str_date).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def get_date_tz(self, str_date):
        timezone = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        date = datetime.strptime(str_date, DEFAULT_SERVER_DATETIME_FORMAT)
        return pytz.UTC.localize(date).astimezone(timezone)

    @api.model
    def get_date_str(self, date):
        return (date.astimezone(pytz.UTC)).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def get_date_with_repl_hour(self, date, final_hour):
        self.ensure_one()
        hour_arr = str(final_hour).split('.')
        hour = int(hour_arr[0])
        minute = int(60 * float('.' + hour_arr[1]))
        return (date.replace(hour=hour, minute=minute).astimezone(pytz.UTC)).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def get_float_hour(self, date):
        minute_arr = str(float(date.minute) / 60).split('.')
        return float('{0}.{1}'.format(date.hour, minute_arr[1]))

    @api.model
    def get_incidence_name(self, attendance_ids, moment, reference_hr):
        return getattr(self, 'get_name_' + moment)(attendance_ids, reference_hr)

    @api.model
    def get_name_before_start_schedule(self, attendance_ids, hour_from):
        if len(attendance_ids.filtered(lambda r: r.hour_to < hour_from)) > 0:
            return 'Check on meal schedule'
        else:
            return 'Check before schedule'

    @api.model
    def get_name_after_end_schedule(self, attendance_ids, hour_to):
        if len(attendance_ids.filtered(lambda r: r.hour_from > hour_to)) > 0:
            return 'Check on meal schedule'
        else:
            return 'Check after schedule'

    def process_att_middle_leave(self, leave_hr_from, leave_hr_to, prev_check_out):
        self.ensure_one()
        new_check_out = self.get_date_with_repl_hour(prev_check_out, leave_hr_from)
        self.write({'check_out': new_check_out})
        check_in = self.get_date_with_repl_hour(prev_check_out, leave_hr_to)
        return self.copy({'check_in': check_in, 'check_out': prev_check_out})

    def process_att_right_leave(self, leave_hr_from, prev_check_out):
        self.ensure_one()
        new_check_out = self.get_date_with_repl_hour(prev_check_out, leave_hr_from)
        self.write({'check_out': new_check_out})

    def process_att_left_leave(self, leave_hr_to, prev_check_in):
        self.ensure_one()
        new_check_in = self.get_date_with_repl_hour(prev_check_in, leave_hr_to)
        self.write({'check_in': new_check_in})

    def add_time_from_incidence(self):
        self.ensure_one()
        if self.check_out:
            return self.create_attendance_obj()
        else:
            raise UserError(_('Check out is not filled'))

    def rollback_adding_time_incidence(self):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Attendance.search([('incidence_id', '=', self.id)]).unlink()

    def rollback_incomplete_logs(self, approve):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        OrigAtt = self.env['original.attendance']
        Attendance.search([('incidence_id', '=', self.id)]).unlink()
        orig_att_ids = OrigAtt.search([('incidence_id', '=', self.id)])
        for orig_att in orig_att_ids:
            self.restore_origin_attendance(orig_att)
        orig_att_ids.unlink()

    def order_dates(self, vals):
        for _id in self:
            att_log_dates = False
            if 'check_in' in vals.keys() and 'check_out' in vals.keys() and vals.get('check_out'):
                att_log_dates = [vals.get('check_in'), vals.get('check_out')]
                if _id.type_incidence == 'incomplete_logs' and _id.check_in != vals.get('check_in'):
                        vals['missing_log_date'] = vals.get('check_in')
            elif 'check_in' in vals.keys() and 'check_out' not in vals.keys() and _id.check_out:
                att_log_dates = [vals.get('check_in'), _id.check_out]
                if _id.type_incidence == 'incomplete_logs' and _id.check_in != vals.get('check_in'):
                        vals['missing_log_date'] = vals.get('check_in')
            elif 'check_in' not in vals.keys() and 'check_out' in vals.keys() and vals.get('check_out'):
                att_log_dates = [_id.check_in, vals.get('check_out')]
                if _id.type_incidence == 'incomplete_logs':
                    vals['missing_log_date'] = vals.get('check_out')

            if att_log_dates:
                vals['check_in'] = min(att_log_dates)
                vals['check_out'] = max(att_log_dates)

    # @api.model
    # def _verify_custom_search_arguments(self, args):
    #     PeriodGp = self.env['payment.period.group']
    #     prev_periods = PeriodGp.get_general_previous_period()
    #
    #     self._verify_custom_argument(args, 'prev_period', 'period_id', 'in', prev_periods)

    @api.model
    def _verify_custom_argument(self, args, field, new_field=False, new_op=False, new_value=False):
        index = self._get_index_search_field(field, args)
        if index != -1:
            if new_field:
                args[index][0] = new_field
            if new_op:
                args[index][1] = new_op
            if new_value:
                args[index][2] = new_value

    def subs_time_from_incidence(self):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Calendar = self.env['resource.calendar']
        date = Calendar.get_object_datetime(self.check_in).date()
        attendance_ids = Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            ('period_id', '=', self.period_id.id)
        ]).filtered(lambda r: Calendar.get_object_datetime(r.check_in).date() == date)

        for att in attendance_ids:
            # incidence wraps attendance
            if att.check_out:
                if self.check_in <= att.check_in and self.check_out >= att.check_out:
                    self.create_origin_attendance(att)
                    att.unlink()
                # incidence in middle of attendance
                elif self.check_in >= att.check_in and self.check_out <= att.check_out:
                    self.create_origin_attendance(att)
                    origin_check_in = deepcopy(att.check_in)
                    origin_check_out = deepcopy(att.check_out)
                    att.unlink()
                    n_att = self.create_attendance_obj(origin_check_in, self.check_in)
                    if n_att.worked_hours <= 0:
                        n_att.unlink()
                    self.create_attendance_obj(self.check_out, origin_check_out)
                    if n_att.worked_hours <= 0:
                        n_att.unlink()
                # incidence check_in in middle of attendance
                elif self.check_in >= att.check_in and self.check_in < att.check_out:
                    self.create_origin_attendance(att)
                    origin_check_in = deepcopy(att.check_in)
                    att.unlink()
                    n_att = self.create_attendance_obj(origin_check_in, self.check_in)
                    if n_att.worked_hours <= 0:
                        n_att.unlink()
                # incidence check_out in middle of attendance
                elif self.check_out <= att.check_out and self.check_out > att.check_in:
                    self.create_origin_attendance(att)
                    origin_check_out = deepcopy(att.check_out)
                    att.unlink()
                    n_att = self.create_attendance_obj(self.check_out, origin_check_out)
                    if n_att.worked_hours <= 0:
                        n_att.unlink()

    def rollback_subs_time_incidence(self, approve):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        OrigAtt = self.env['original.attendance']
        Attendance.search([('incidence_id', '=', self.id)]).unlink()
        orig_att_ids = OrigAtt.search([('incidence_id', '=', self.id)])
        for orig_att in orig_att_ids:
            self.restore_origin_attendance(orig_att)
        orig_att_ids.unlink()

    def send_to_draft_incidence(self):
        for _id in self:
            if _id.state == 'approved' and _id.type_incidence == 'leave':
                _id.rollback_subs_time_incidence()
            elif _id.type_incidence == 'incomplete_logs':
                _id.rollback_incomplete_logs()
            elif _id.state == 'approved':
                _id.rollback_adding_time_incidence()

        self.write({'state': 'draft'})

    def reject_incidence(self):
        self.write({'state': 'rejected'})

    def approve_incomplete_logs(self):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        if self.check_out:

            # Get attendance generated with old set of log dates
            att_ids = Attendance.search([
                ('employee_id', '=', self.employee_id.id),
                ('date_computed', '=', self.date_computed)
            ])

            # Save backup of old attendance
            for att in att_ids:
                self.create_origin_attendance(att)

            # Delete old attendances and your incidences except for this
            att_ids.unlink()
            self.search([
                ('employee_id', '=', self.employee_id.id),
                ('date_computed', '=', self.date_computed),
                ('id', '!=', self.id)
            ]).unlink()

            self.write({'state': 'approved'})
            ctx = self._get_context_to_approve_incomplete_attendance_log()
            return {
                'type': 'ir.actions.client',
                'tag': 'approve_incomplete_attendance_log',
                'context': ctx
            }

        else:
            raise ValidationError(_('Warning! Check_out must be different to null'))

    def create_origin_attendance(self, attendance):
        self.ensure_one()
        OrigAtt = self.env['original.attendance']
        OrigAtt.create({
            'incidence_id': self.id,
            'orig_incidence_id': attendance.incidence_id.id,
            'is_modified': attendance.is_modified,
            'employee_id': attendance.employee_id.id,
            'check_in': attendance.check_in,
            'check_out': attendance.check_out,
            'period_id': attendance.period_id.id,
            'date_computed': attendance.date_computed,
            'day_computed': attendance.day_computed,
            'check_in_hour': attendance.check_in_hour,
            'check_out_hour': attendance.check_out_hour
        })

    def restore_origin_attendance(self, attendance):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Attendance.with_context(approve_incidence=True).create({
            'incidence_id': attendance.orig_incidence_id.id,
            'is_modified': attendance.is_modified,
            'employee_id': attendance.employee_id.id,
            'check_in': attendance.check_in,
            'check_out': attendance.check_out,
            'period_id': attendance.period_id.id,
            'date_computed': attendance.date_computed,
            'day_computed': attendance.day_computed,
            'check_in_hour': attendance.check_in_hour,
            'check_out_hour': attendance.check_out_hour
        })

    def create_attendance_obj(self, check_in=False, check_out=False):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        return Attendance.with_context(approve_incidence=True).create({
            'incidence_id': self.id,
            'employee_id': self.employee_id.id,
            'check_in': check_in and check_in or self.check_in,
            'check_out': check_out and check_out or self.check_out,
            'period_id': self.period_id.id,
            'date_computed': self.date_computed,
            'day_computed': self.day_computed,
            'check_in_hour': self.check_in_hour,
            'check_out_hour': self.check_out_hour
        })

    def create_attendance_n_incidence_from_commands(self, attendance, incidences):
        self.ensure_one()
        self.employee_id.with_context(approve_incidence=True).write({'attendance_ids': attendance, 'incidence_ids': incidences})

    def approve_incidence(self):
        for _id in self:
            if _id.type_incidence == 'leave':
                _id.subs_time_from_incidence()
            elif _id.type_incidence == 'incomplete_logs':
                if len(self) == 1:
                    return _id.approve_incomplete_logs()
            else:
                _id.add_time_from_incidence()

            if _id.productivity_block:
                Blocks = self.env['hr.productivity.block']
                block_type = 'inactive' if _id.type_incidence in ['leave', 'holiday', 'holiday_company'] else 'active'
                if _id.type_incidence == 'omission':
                    Blocks.modify_delay_blocks(_id.employee_id, _id.check_in, self.env.user, set_fixed=False)
                if block_type == 'inactive':
                    Blocks.move_tracking(_id.employee_id, _id.check_in, _id.check_out)
                Blocks.create({'start_date': _id.check_in,
                               'end_date': _id.check_out,
                               'employee_id': _id.employee_id.id,
                               'block_type': block_type,
                               'block_origin': 'incidence',
                               'incidence_id': _id.id})
                Blocks.rebuild_blocks(_id.employee_id)
                # Restore fixed duration
                if _id.type_incidence == 'omission':
                    Blocks.modify_delay_blocks(_id.employee_id, _id.check_in, self.env.user, set_fixed=True)

        self.write({'state': 'approved'})

    @api.model
    def _get_index_search_field(self, field, args):
        try:
            index = list(map(lambda r: field in r, args)).index(True)
        except:
            index = -1
        return index

    def _get_context_to_approve_incomplete_attendance_log(self):
        self.ensure_one()
        AttLog = self.env['attendance.log']
        # Get list of log dates that were made by the employee
        log_list = AttLog.search([
            ('employee_id', '=', self.employee_id.id),
            ('date_computed', '=', self.date_computed),
        ]).mapped('attendance_log_date')
        log_list.append(self.missing_log_date)
        return {
            'attendance_log_dates': log_list,
            'employee_id': self.employee_id.id
        }

    @api.model
    def save_massive_incidence(self, new_records, records_to_delete):
        if new_records and len(new_records) > 0:
            fnames = new_records[0].keys()
            values = ''
            for record in new_records:
                values += '('
                rec = ''
                for key in fnames:
                    value = record[key]
                    if type(value).__name__ == 'str' and value != 'NULL':
                        rec += "'" + value + "'" + ','
                    else:
                        rec += str(value) + ','
                values += rec[:-1] + '),'
            values = values[:-1]

            sql = 'INSERT INTO attendance_incidence(' + ', '.join(fnames) + ') VALUES ' + values + ' RETURNING id'
            self.env.cr.execute(sql)
            ids = [r[0] for r in self.env.cr.fetchall()]
            self.env.cache.invalidate()

            _ids = self.browse(ids)
            _ids._recompute_todo(self._fields['structure_type_id'])
            _ids._recompute_todo(self._fields['worked_hours'])
            _ids._recompute_todo(self._fields['worked_hours'])
            _ids._recompute_todo(self._fields['period_id'])
            _ids._recompute_todo(self._fields['qty_real_logs'])
            _ids._recompute_todo(self._fields['count'])
            self.recompute()

        if records_to_delete and len(records_to_delete) > 0:
            self.browse(records_to_delete).unlink()


class OriginalAttendance(models.Model):
    _name = 'original.attendance'
    _description = 'original.attendance'


    incidence_id = fields.Many2one('attendance.incidence', ondelete='cascade')
    orig_incidence_id = fields.Many2one('attendance.incidence')
    is_modified = fields.Boolean(default=False)

    employee_id = fields.Many2one('hr.employee', ondelete='cascade', index=True)
    check_in = fields.Datetime()
    check_out = fields.Datetime()
    # period_id = fields.Many2one('payment.period', compute='_compute_period', store=True)
    period_id = fields.Many2one('payment.period', ondelete='restrict')
    # date_computed = fields.Date('Date', compute='_compute_date', store=True)
    date_computed = fields.Date('Date')
    day_computed = fields.Char('Day')
    check_in_hour = fields.Float('CheckIn')
    check_out_hour = fields.Float('CheckOut')

