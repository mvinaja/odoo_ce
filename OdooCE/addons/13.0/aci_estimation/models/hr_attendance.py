# -*- coding: utf-8 -*-

from datetime import datetime
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

from . import general_tools


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'
    _order = 'period_id desc, employee_id, check_in asc'

    incidence_id = fields.Many2one('attendance.incidence')
    is_modified = fields.Boolean(default=False)
    schedule_delay = fields.Boolean('Delay in schedule', default=False)

    date_computed = fields.Date('Date', compute='_compute_date', store=True,
        inverse='inverse_value')
    day_computed = fields.Char('Day', compute='_compute_date', store=True,
        inverse='inverse_value')
    check_in_hour = fields.Float('CheckIn', compute='_compute_hours', store=True,
        inverse='inverse_value')
    check_out_hour = fields.Float('CheckOut', compute='_compute_hours', store=True,
        inverse='inverse_value')
    period_id_computed = fields.Many2one('payment.period', string='Period Com.',
        compute='_compute_period', index=True, ondelete='restrict', search='_search_period', compute_sudo=True)
    period_id = fields.Many2one('payment.period', compute='_compute_period',
        string='Period', store=True, inverse='inverse_value', ondelete='restrict', compute_sudo=True)
    structure_type_id = fields.Many2one(
        'hr.payroll.structure.type', compute='_compute_structure_type', store=True, string='Salary Structure Type')
    department_id = fields.Many2one(related='employee_id.department_id', readonly=True, store=True)
    # Dummy to search
    prev_period = fields.Boolean()

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """ Verifies the validity of the attendance record compared to the others from the same employee.
            For the same employee we must have :
                * maximum 1 "open" attendance record (without check_out)
                * no overlapping time slices with previous employee records
        """
        context = self.env.context
        for attendance in self:
            # we take the latest attendance before our check_in time and check it doesn't overlap with ours
            last_attendance_before_check_in = self.env['hr.attendance'].search([
                ('employee_id', '=', attendance.employee_id.id),
                ('check_in', '<=', attendance.check_in),
                ('id', '!=', attendance.id),
            ], order='check_in desc', limit=1)
            if last_attendance_before_check_in and last_attendance_before_check_in.check_out and last_attendance_before_check_in.check_out >= attendance.check_in:
                if not context.get('approve_incidence', False):
                    raise ValidationError(_("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s") % {
                        'empl_name': attendance.employee_id.name,
                        'datetime': fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in))),
                    })

            if not attendance.check_out:
                # if our attendance is "open" (no check_out), we verify there is no other "open" attendance
                no_check_out_attendances = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_out', '=', False),
                    ('id', '!=', attendance.id),
                ])
                if not context.get('approve_incidence', False):
                    if no_check_out_attendances:
                        raise ValidationError(_("Cannot create new attendance record for %(empl_name)s, the employee hasn't checked out since %(datetime)s") % {
                            'empl_name': attendance.employee_id.name,
                            'datetime': fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(no_check_out_attendances.check_in))),
                        })
            else:
                # we verify that the latest attendance with check_in time before our check_out time
                # is the same as the one before our check_in time computed before, otherwise it overlaps
                last_attendance_before_check_out = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_in', '<=', attendance.check_out),
                    ('id', '!=', attendance.id),
                ], order='check_in desc', limit=1)
                if not context.get('approve_incidence', False):
                    if last_attendance_before_check_out and last_attendance_before_check_in != last_attendance_before_check_out:
                        raise ValidationError(_("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s") % {
                            'empl_name': attendance.employee_id.name,
                            'datetime': fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(last_attendance_before_check_out.check_in))),
                        })

    @api.model
    def _read_group_process_groupby(self, gb, query):
        response = super(HrAttendance, self)._read_group_process_groupby(gb, query)
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
                        FROM hr_attendance a
                    WHERE %(date_to)s >= a.date_computed
                        AND %(date_from)s <= a.date_computed
                    GROUP BY a.id""", {'date_from': period.from_date,
                                       'date_to': period.to_date,})
            ids.extend([row[0] for row in self._cr.fetchall()])
        return [('id', 'in', ids)]

    def inverse_value(self):
        return 'done'

    @api.depends('check_in')
    def _compute_date(self):
        Calendar = self.env['resource.calendar']
        for _id in self:
            date = Calendar.get_object_datetime(_id.check_in)
            _id.date_computed = date.date()
            _id.day_computed = date.strftime('%A')

    @api.depends('check_in', 'check_out')
    def _compute_hours(self):
        Calendar = self.env['resource.calendar']
        for _id in self:
            date = Calendar.get_object_datetime(_id.check_in)
            _id.check_in_hour = general_tools.get_float_from_time(date)
            if _id.check_out:
                date = Calendar.get_object_datetime(_id.check_out)
                _id.check_out_hour = general_tools.get_float_from_time(date)

    # @api.depends('employee_id', 'check_in', 'check_out', 'period_id_computed.to_date', 'period_id_computed.from_date')
    @api.depends('employee_id', 'check_in', 'check_out', 'date_computed', 'period_id_computed.to_date', 'period_id_computed.from_date')
    def _compute_period(self):
        """Links the attendance to the corresponding period
        """
        Contract = self.env['hr.contract']
        # Calendar = self.env['resource.calendar']
        for _id in self:
            contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
            # check_in = Calendar.get_object_datetime(_id.check_in)
            if contract_id:
                for grp in contract_id.period_group_id:
                    corresponding_period = self.env['payment.period'].search(
                        # [('to_date', '>=', check_in), ('from_date', '<=', check_in),
                        [('to_date', '>=', _id.date_computed), ('from_date', '<=', _id.date_computed),
                        ('group_id', '=', grp.period_group_id.id)], limit=1)
                    if corresponding_period:
                        _id.period_id_computed = corresponding_period[0]
                        _id.period_id = corresponding_period[0]

    @api.depends('employee_id')
    def _compute_structure_type(self):
        Contract = self.env['hr.contract']
        for _id in self:
            contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
            if contract_id:
                _id.structure_type_id = contract_id.structure_type_id.id

    def check_schedule_leaves(self, incidence=False):
        Contract = self.env['hr.contract']
        Calendar = self.env['resource.calendar']
        for _id in self:
            contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
            if not contract_id or not _id.check_out:
                continue
            calendar_id = contract_id.resource_calendar_id
            if not calendar_id:
                continue

            check_in = Calendar.get_object_datetime(_id.check_in)
            check_in_hour = general_tools.get_float_from_time(check_in)
            check_out = Calendar.get_object_datetime(_id.check_out)
            check_out_hour = general_tools.get_float_from_time(check_out)
            weekday = check_in.weekday()

            leave_ids = calendar_id.schedule_leave_ids.filtered(lambda r: int(r.dayofweek) == int(weekday))
            unlink = False
            for leave in leave_ids:
                leave_hr_from = leave.hour_from
                leave_hr_to = leave.hour_to

                # Leave wraps attendance
                if leave_hr_from <= check_in_hour and leave_hr_to >= check_out_hour:
                    unlink = True
                    break
                # Leave in middle of attendance
                elif leave_hr_from >= check_in_hour and leave_hr_to <= check_out_hour:
                    new_att = _id.process_att_middle_leave(leave_hr_from, leave_hr_to, check_out, incidence)
                    check_out_hour = leave_hr_from
                    check_out = _id.get_date_obj_with_repl_hour(check_out, check_out_hour)
                    if new_att.worked_hours > 0:
                        new_att.check_schedule_leaves()
                    else:
                        new_att.unlink()
                # Leave hour_from in middle of attendance
                elif leave_hr_from >= check_in_hour and leave_hr_from < check_out_hour:
                    _id.process_att_right_leave(leave_hr_from, check_out)
                    check_out_hour = leave_hr_from
                    check_out = _id.get_date_obj_with_repl_hour(check_out, check_out_hour)
                # Leave hour_to in middle of attendance
                elif leave_hr_to <= check_out_hour and leave_hr_to > check_in_hour:
                    _id.process_att_left_leave(leave_hr_to, check_in)
                    check_in_hour = leave_hr_to
                    check_in = _id.get_date_obj_with_repl_hour(check_in, check_in_hour)

                if _id.worked_hours <= 0:
                    unlink = True
                    break

            if unlink or _id.worked_hours <= 0:
                _id.unlink()

    def process_att_middle_leave(self, leave_hr_from, leave_hr_to, prev_check_out, incidence=False):
        self.ensure_one()
        new_check_out = self.get_date_with_repl_hour(prev_check_out, leave_hr_from)
        self.with_context(approve_incidence=True).write({'check_out': new_check_out})
        check_in = self.get_date_with_repl_hour(prev_check_out, leave_hr_to)
        check_out = self.get_date_str(prev_check_out)
        new_att_dict = {
            'employee_id': self.employee_id.id,
            'check_in': check_in,
            'check_out': check_out
        }
        if incidence:
            new_att_dict['incidence_id'] = incidence.id
        return self.with_context(approve_incidence=True).create(new_att_dict)

    def process_att_right_leave(self, leave_hr_from, prev_check_out):
        self.ensure_one()
        new_check_out = self.get_date_with_repl_hour(prev_check_out, leave_hr_from)
        self.with_context(approve_incidence=True).write({'check_out': new_check_out})

    def process_att_left_leave(self, leave_hr_to, prev_check_in):
        self.ensure_one()
        new_check_in = self.get_date_with_repl_hour(prev_check_in, leave_hr_to)
        self.with_context(approve_incidence=True).write({'check_in': new_check_in})

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
    def get_date_with_repl_hour(self, date, final_hour):
        self.ensure_one()
        f_date = self.get_date_obj_with_repl_hour(date, final_hour)
        return self.get_date_str(f_date)

    @api.model
    def get_date_obj_with_repl_hour(self, date, final_hour):
        self.ensure_one()
        hour_arr = str(final_hour).split('.')
        hour = int(hour_arr[0])
        minute = int(60 * float('.' + hour_arr[1]))
        return date.replace(hour=hour, minute=minute)

    @api.model
    def get_date_str(self, date):
        return (date.astimezone(pytz.UTC)).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

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

    @api.model
    def _get_index_search_field(self, field, args):
        try:
            index = list(map(lambda r: field in r, args)).index(True)
        except:
            index = -1
        return index

    @api.model
    def save_massive_attendance(self, new_records, records_to_delete):
        if new_records and len(new_records) > 0:
            fnames = new_records[0].keys()
            values = ''
            for record in new_records:
                values += '('
                rec = ''
                for key in fnames:
                    value = record[key]
                    rec += (type(value).__name__ == 'str' and "'" + value + "'" or str(value)) + ','
                values += rec[:-1] + '),'
            values = values[:-1]

            sql = 'INSERT INTO hr_attendance(' + ', '.join(fnames) + ') VALUES ' + values + ' RETURNING id'
            self.env.cr.execute(sql)
            ids = [r[0] for r in self.env.cr.fetchall()]
            self.env.cache.invalidate()

            _ids = self.browse(ids)
            _ids._recompute_todo(self._fields['structure_type_id'])
            _ids._recompute_todo(self._fields['period_id'])
            _ids._recompute_todo(self._fields['department_id'])
            _ids._recompute_todo(self._fields['worked_hours'])
            self.recompute()

        if records_to_delete and len(records_to_delete) > 0:
            self.browse(records_to_delete).unlink()


class AttendanceSecurityLog(models.Model):
    _name = 'attendance.security.log'
    _description = 'attendance.security.log'

    attendance_id = fields.Many2one(
        'hr.attendance', required=True, ondelete='cascade')
    original_check_in = fields.Datetime()
    original_check_out = fields.Datetime()
    dummy_check_in = fields.Datetime(
        'Original CheckIn', compute='_compute_attendance_data', store=True)
    dummy_check_out = fields.Datetime(
        'Original CheckOut', compute='_compute_attendance_data', store=True)

    new_check_in = fields.Datetime('New Check In')
    new_check_out = fields.Datetime('New Check Out')

    @api.model
    def create(self, vals):
        att_vals = {}
        if 'new_check_in' in vals.keys() and vals.get('new_check_in'):
            att_vals['check_in'] = vals.get('new_check_in')
            att_vals['is_modified'] = True
        if 'new_check_out' in vals.keys() and vals.get('new_check_out'):
            att_vals['check_out'] = vals.get('new_check_out')
            att_vals['is_modified'] = True

        att_log_id = super(AttendanceSecurityLog, self).create(vals)
        att_log_id.write({
            'original_check_in': att_log_id.dummy_check_in,
            'original_check_out': att_log_id.dummy_check_out
        })

        attendance_id = self.env['hr.attendance'].browse(vals.get('attendance_id'))
        attendance_id.write(att_vals)
        return att_log_id

    def write(self, vals):
        if 'new_check_in' in vals.keys() or 'new_check_out' in vals.keys():
            for _id in self:
                att_vals = {'is_modified': True}
                _id.validate_modified_flag(vals, att_vals)

                if 'new_check_in' in vals.keys() and vals.get('new_check_in'):
                    att_vals['check_in'] = vals.get('new_check_in')
                elif 'new_check_in' in vals.keys() and not vals.get('new_check_in'):
                    att_vals['check_in'] = _id.original_check_in

                if 'new_check_out' in vals.keys() and vals.get('new_check_out'):
                    att_vals['check_out'] = vals.get('new_check_out')
                elif 'new_check_in' in vals.keys() and not vals.get('new_check_in'):
                    att_vals['check_in'] = _id.original_check_in

                _id.attendance_id.write(att_vals)
        return super(AttendanceSecurityLog, self).write(vals)

    @api.depends('attendance_id')
    def _compute_attendance_data(self):
        for _id in self:
            if _id.attendance_id.check_in and not _id.original_check_in:
                _id.dummy_check_in = _id.attendance_id.check_in
            elif _id.original_check_in:
                _id.dummy_check_in = _id.original_check_in

            if _id.attendance_id.check_out and not _id.original_check_out:
                _id.dummy_check_out = _id.attendance_id.check_out
            elif _id.original_check_out:
                _id.dummy_check_out = _id.original_check_in

    def validate_modified_flag(self, vals, att_vals):
        self.ensure_one()
        if 'new_check_in' in vals.keys() and not vals.get('new_check_in') and 'new_check_out' in vals.keys() and not vals.get('new_check_out'):
            att_vals['is_modified'] = False
        elif 'new_check_in' in vals.keys() and not vals.get('new_check_in') and 'new_check_out' not in vals.keys():
            if not self.new_check_out:
                att_vals['is_modified'] = False
        elif 'new_check_out' in vals.keys() and not vals.get('new_check_out') and 'new_check_in' not in vals.keys():
            if not self.new_check_in:
                att_vals['is_modified'] = False
