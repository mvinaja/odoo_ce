# -*- coding: utf-8 -*-

from io import BytesIO
import base64

from datetime import datetime, timedelta

from odoo import models, fields, api
from odoo.tools.mimetypes import guess_mimetype
from odoo.exceptions import UserError


class AttendanceLogActions(models.TransientModel):
    _name = 'attendance.log.actions'
    _description = 'attendance.log.actions'

    @api.model
    def _get_years_options(self):
        vals = []
        pointer_year = 2017
        while pointer_year < 2050:
            vals.append((str(pointer_year), str(pointer_year)))
            pointer_year += 1
        return vals

    @api.model
    def _get_hour_options(self):
        vals = []
        pointer_hour = 0
        while pointer_hour < 24:
            hour = '%02d' % (pointer_hour)
            vals.append((hour, hour))
            pointer_hour += 1
        return vals

    @api.model
    def _get_minutes_options(self):
        vals = []
        pointer_minutes = 0
        while pointer_minutes < 60:
            minutes = '%02d' % (pointer_minutes)
            vals.append((minutes, minutes))
            pointer_minutes += 1
        return vals

    @api.model
    def _get_default_year(self):
        return str(datetime.now().year)

    dat_file = fields.Binary(
        'Dat File', filters='*.dat', help='.dat file')
    dat_name = fields.Char('File Name')

    year = fields.Selection(
        selection=_get_years_options, default=_get_default_year, index=True)
    payment_period_grp = fields.Many2one('payment.period.group', 'Payment Period Group')
    period_id = fields.Many2one('payment.period', 'Period', ondelete='restrict')
    date_from = fields.Date('Date From', compute='_compute_period_dates')
    date_to = fields.Date('Date To', compute='_compute_period_dates')
    employee_ids = fields.Many2many('hr.employee', 'aci_attendance_payment__hr_employee',
        'aci_attendance_payment', 'employee_id', string='Employees')

    all_employees = fields.Boolean('All Employees', default=True)

    hour = fields.Selection(selection=_get_hour_options)
    minutes = fields.Selection(selection=_get_minutes_options)
    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
        ], 'Day of Week')
    date = fields.Date()
    exclude_employee_ids = fields.Many2many('hr.employee', 'attendance_log_actions__hr_employee',
        'attendance_log_actions', 'employee_id', string='Exclude')
    to_employee_ids = fields.Many2many('hr.employee',
        'to_employee_attendance_log_actions__hr_employee',
        'attendance_log_actions', 'employee_id', string='To Employees')

    @api.depends('period_id')
    def _compute_period_dates(self):
        for _id in self:
            if _id.period_id:
                _id.date_from = _id.period_id.from_date
                _id.date_to = _id.period_id.to_date

    @api.onchange('year')
    def onchange_year(self):
        self.payment_period_grp = False
        self.period_id = False
        return {'domain': {'payment_period_grp': [('year', '=', self.year)]}}

    @api.onchange('payment_period_grp')
    def onchange_payment_period_grp(self):
        if self.payment_period_grp:
            PeriodGpo = self.env['payment.period.group']
            period_gpo = PeriodGpo.search([('id', '=', self.payment_period_grp.id)])
            prev_period = period_gpo.get_previous_period()
            self.period_id = prev_period.id

    @api.onchange('period_id')
    def onchange_payment_period(self):
        ids_employee = self.env['hr.contract'].search([('period_group_id', '=', self.period_id.group_id.id)]).mapped('employee_id').ids
        return {'domain': {'to_employee_ids': [('id', 'in', ids_employee)]}}

    def parse_and_import_button(self):
        self.ensure_one()
        AttLog = self.env['attendance.log']

        pin_list = self._get_pin_employees_by_period_group(self.payment_period_grp)
        self._validate_file(self.dat_file)
        new_records = self._get_records_file(self.dat_file, self.all_employees,
                                         self.employee_ids.ids, pin_list)
        existing_records = AttLog.search([
            ('period_id', '=', self.period_id.id)
        ]).mapped(lambda r: r.employee_id and (str(r.employee_id.id) + '--' + r.attendance_log_date) or None)

        return {
            'type': 'ir.actions.client',
            'tag': 'import_attendance_log',
            'context': {
                'date_from': self.date_from,
                'date_to': self.date_to,
                'new_records': new_records,
                'existing_records': existing_records
            }
        }

    def discard_nearby_button(self):
        self.ensure_one()
        AttLog = self.env['attendance.log']
        Calendar = self.env['resource.calendar']
        att_log_ids = AttLog.search([('reviewed', '=', False)])
        if att_log_ids:
            dict_logs = dict(att_log_ids.mapped(lambda r:\
                (r.id, (Calendar.get_object_datetime(r.attendance_log_date), r.employee_id))))

            to_discard = {}
            for id_, (date, employee_id) in dict_logs.items():
                nearby = dict([(_id, date_emp[0]) for _id, date_emp in dict_logs.items()\
                            if (abs((date_emp[0] - date).total_seconds()) / 60) < 10\
                            and employee_id == date_emp[1] and id_ != _id])

                if nearby:
                    keys = list(nearby.keys())
                    keys.append(id_)
                    keys.sort()
                    keys = ''.join([str(k) for k in keys])
                    to_discard.setdefault((employee_id, keys), {}).update(nearby)

            to_discard = [k for vals in to_discard.values()\
                          for k in vals.keys() if k != min(vals, key=vals.get)]
            AttLog.browse(to_discard).write({'discarded': True})
        att_log_ids.write({'reviewed': True})

    def generate_masssive_checks_by_period_button(self):
        self.ensure_one()
        ctx = self._get_context_to_massive_action()
        return {
            'type': 'ir.actions.client',
            'tag': 'generate_massive_logs',
            'context': ctx
        }

    @api.model
    def _validate_file(self, file):
        VALID_MIME_TYPES = {
            'application/octet-stream': 'dat',
            'zz-application/zz-winassoc-dat': 'dat'
        }
        if not VALID_MIME_TYPES.get(guess_mimetype(file), False):
            raise UserError(_('The file type is not valid'))

    @api.model
    def _get_records_file(self, file, all_employees, ids_employee, pin_list):
        KEYS_MAP = {0: 'pin', 1: 'attendance_log_date'}
        file_data = BytesIO(base64.decodestring(self.dat_file))
        records = []
        for line in file_data.readlines():
            line_data = line.decode('utf-8', 'backslashreplace')
            values = dict([(KEYS_MAP.get(i), f.strip()) for i, f in\
                      enumerate(line_data.split('\t')) if i in KEYS_MAP.keys()])

            if (all_employees and values['pin'] in pin_list.keys())\
                    or (not self.all_employees and values['pin'] in pin_list.keys()\
                        and pin_list[values['pin']] in ids_employee):
                values['employee_id'] = pin_list[values['pin']]
                records.append(values)

        return records

    @api.model
    def _get_pin_employees_by_period_group(self, period_group):
        return dict(self.env['hr.contract'].search([
            ('period_group_id', '=', period_group.id)
        ]).mapped('employee_id').mapped(lambda r: (r.pin, r.id)))

    def _get_employees_schedule(self):
        self.ensure_one()
        excluded_employees = [employee_id.id for employee_id in self.exclude_employee_ids]

        employee_calendar = dict(self.env['hr.contract'].search([
            ('period_group_id', '=', self.period_id.group_id.id)
        ]).mapped(lambda r: (r.employee_id, r.resource_calendar_id)))
        calendars = {}
        employee_schedule = {}
        for employee_id, calendar_id in employee_calendar.items():
            if (self.to_employee_ids and employee_id.id in self.to_employee_ids.ids)\
                    or (not self.to_employee_ids and employee_id.id not in excluded_employees):
                if calendar_id.id not in calendars.keys():
                    calendars[calendar_id.id] = calendar_id.get_extremes_by_day()
                employee_schedule[employee_id.id] = calendars[calendar_id.id]
        return employee_schedule

    def _get_dates_range(self):
        self.ensure_one()
        Calendar = self.env['resource.calendar']
        date_range = {}
        str_from_date = self.period_id.from_date
        from_date = Calendar.get_object_date(str_from_date)
        str_to_date = self.period_id.to_date
        to_date = Calendar.get_object_date(str_to_date)
        for i in range(0, (to_date - from_date).days):
            pointer_date = from_date + timedelta(days=i)
            date_range[Calendar.get_string_date(pointer_date)] = pointer_date.weekday()
        date_range[str_to_date] = to_date.weekday()

        return str_from_date, str_to_date, date_range

    def _get_context_to_massive_action(self):
        employee_schedule = self._get_employees_schedule()
        str_from_date, str_to_date, date_range = self._get_dates_range()

        ctx = {
            'hour': self.hour,
            'minutes': self.minutes,
            'employee_schedule': employee_schedule,
            'date_range': date_range
        }
        if self.date:
            if self.date not in date_range.keys():
                raise UserError(_('Date must be between ' + str_from_date + ' - ' + str_to_date))
            ctx['date'] = self.date
        elif self.dayofweek:
            ctx['dayofweek'] = self.dayofweek
        return ctx
