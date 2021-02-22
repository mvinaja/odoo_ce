# -*- coding: utf-8 -*-

import pytz
from datetime import datetime

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class HrAttendancePayment(models.TransientModel):
    _name = 'hr.attendance.actions'
    _description = 'hr.attendance.actions'

    @api.model
    def _get_years_options(self):
        vals = []
        pointer_year = 2017
        while pointer_year < 2050:
            vals.append((str(pointer_year), str(pointer_year)))
            pointer_year += 1
        return vals

    @api.model
    def _get_default_year(self):
        return str(datetime.now().year)

    year = fields.Selection(
        selection=_get_years_options, default=_get_default_year, index=True)
    period_grp_id = fields.Many2one('payment.period.group', 'Payment Period Group')
    period_id = fields.Many2one('payment.period', 'Period', ondelete='restrict')
    date_from = fields.Date('Date From', compute='_compute_period_dates')
    date_to = fields.Date('Date To', compute='_compute_period_dates')
    all_employees = fields.Boolean('All Employees', default=True)
    employee_ids = fields.Many2many('hr.employee', 'hr_attendance_actions__hr_employee',
        'hr_attendance_actions', 'employee_id', string='Employees')
    all_dates = fields.Boolean('All Dates', default=True)
    search_date = fields.Date('Date')

    @api.depends('period_id')
    def _compute_period_dates(self):
        for _id in self:
            if _id.period_id:
                _id.date_from = _id.period_id.from_date
                _id.date_to = _id.period_id.to_date

    @api.onchange('year')
    def onchange_year(self):
        self.period_grp_id = False
        self.period_id = False
        return {'domain': {'period_grp_id': [('year', '=', self.year)]}}

    @api.onchange('period_grp_id')
    def onchange_period_group(self):
        if self.period_grp_id:
            PeriodGpo = self.env['payment.period.group']

            period_gpo = PeriodGpo.search([('id', '=', self.period_grp_id.id)])
            prev_period = period_gpo.get_previous_period()
            self.period_id = prev_period.id

            contract_rel_ids = self.env['hr.contract'].search([('period_group_id', '=', self.period_grp_id.id)])
            employee_ids = contract_rel_ids.mapped('employee_id')
            return {'domain': {'employee_ids': [('id', 'in', employee_ids.ids)]}}

    # def _init_dates(self):
    #     self.ensure_one()
    #     self.aux_date_from = self._get_date_obj_formed(self.date_from, '00', '00', '00')
    #     self.aux_date_to = self._get_date_obj_formed(self.date_to, '23', '59', '59')

    def compute_attendance_button(self):
        """ Procesar attendance
        Este metodo se dispara en el botton "compute attendance" en la interfaz de attendance:
        attendance > manage attendance > attendances.

        Procesa los registros de checadas de empleados de la opcion attendance log
        (attendance > manage attendance > attendance log) para generar registros de attendance
        e incidencias.
        """
        self.ensure_one()
        ctx = self._get_context_to_compute_attendance()
        return {
            'type': 'ir.actions.client',
            'tag': 'compute_attendance',
            'context': ctx
        }

    def compute_individual_attendance_button(self):
        self.ensure_one()
        # self._init_dates()
        self._unlink_computed_objects_by_employees()
        if self.search_date:
            records = self._get_attendance_logs(self.employee_ids, self.search_date)
        else:
            records = self._get_attendance_logs(self.employee_ids)
        records = self.group_by_employee(records)
        self._save_attendances(records)

    def get_employees_pin_in_period_group(self):
        self.ensure_one()
        return dict(self.env['hr.contract'].search([
            ('period_group_id', '=', self.period_grp_id.id)
        ]).mapped('employee_id').mapped(lambda r: (r.pin, r.id)))

    @api.model
    def _get_date_object(self, str_date):
        return self._get_date_tz(datetime.strptime(str_date, DEFAULT_SERVER_DATETIME_FORMAT))

    @api.model
    def _get_date_obj_formed(self, str_date, hour, minute, second):
        self.ensure_one()
        tz = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        str_date = '{0} {1}:{2}:{3}'.format(str_date, hour, minute, second)
        return datetime.strptime(str_date, DEFAULT_SERVER_DATETIME_FORMAT).replace(tzinfo=tz)

    @api.model
    def _get_date_tz(self, date):
        tz = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        return pytz.UTC.localize(date).astimezone(tz)

    @api.model
    def get_date_str(self, date):
        return (date.astimezone(pytz.UTC)).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    def _get_attendance_logs(self, employee_ids=False, date=False):
        self.ensure_one()
        AttLog = self.env['attendance.log']
        search = [('period_id', '=', self.period_id.id),('discarded', '=', False)]
        if employee_ids:
            search.append(('employee_id', 'in', employee_ids.ids))
        if date:
            search.append(('date_computed', '=', date))
        return AttLog.search(search).mapped(lambda r: (r.employee_id, r.attendance_log_date))

    def _get_context_to_compute_attendance(self):
        self.ensure_one()
        employee_attendance = self._get_attendace_logs()
        self._attach_schedule_and_tolerance_to_attendance(employee_attendance)
        return {
            'employee_attendance': employee_attendance,
            'records_to_delete': self._get_records_to_delete()
        }

    def _get_attendace_logs(self):
        self.ensure_one()
        AttLog = self.env['attendance.log']
        _fields = {'attendance_log_date': 'str', 'employee_id': 'm2o'}
        att_logs = {}
        employee_ids = self.all_employees and False or self.employee_ids.ids
        search_date = self.all_dates and False or self.search_date
        for rec in AttLog.get_attendance_logs_by_period_mapped(self.period_id, _fields, employee_ids, search_date):
            att_logs.setdefault(rec['employee_id'], {'log_dates': []})
            att_logs[rec['employee_id']]['log_dates'].append(rec['attendance_log_date'])
        return att_logs

    def _get_records_to_delete(self):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Incidence = self.env['attendance.incidence']
        return {
            'attendance': self._get_rec_to_delete(Attendance),
            'incidence': self._get_rec_to_delete(Incidence)
        }

    def _get_rec_to_delete(self, TargetModel):
        self.ensure_one()
        domain = [('period_id', '=', self.period_id.id)]
        if not self.all_employees:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if not self.all_dates:
            domain.append(('date_computed', '=', self.search_date))
        record_ids = TargetModel.search(domain)
        if record_ids and len(record_ids) > 0:
            return record_ids.ids
        return []

    @api.model
    def _attach_schedule_and_tolerance_to_attendance(self, employee_attendance):
        Contract = self.env['hr.contract']
        calendars = {}
        for id_employee in list(employee_attendance.keys()):
            contract_id = Contract.search([('employee_id', '=', id_employee)], limit=1)
            calendar_id = contract_id.resource_calendar_id
            if not calendar_id in calendars:
                calendars[calendar_id] = calendar_id.get_schedule_distribution()

            employee_attendance[id_employee]['schedule'] = calendars[calendar_id]
            employee_attendance[id_employee]['tolerance'] = {
                'type': contract_id.tolerance, 'time': contract_id.tolerance_time}


    def group_by_employee(self, records):
        self.ensure_one()
        Calendar = self.env['resource.calendar']
        dataset = {}
        for r in records:
            employee_id = r[0]
            log_date = r[1]
            date = Calendar.get_object_datetime(log_date).date()
            dataset.setdefault((employee_id, date), [])
            dataset[(employee_id, date)].append(Calendar.get_object_datetime(log_date))
        return dataset

    def _save_attendances(self, records):
        self.ensure_one()
        Contract = self.env['hr.contract']
        employee_ids = []
        for k, dates in records.items():
            employee_id = k[0]
            contract_id = Contract.search([('employee_id', '=', employee_id.id)], limit=1)
            if contract_id:
                calendar_id = contract_id.resource_calendar_id
                if calendar_id:
                    self.create_attendance(employee_id, contract_id, dates, calendar_id)
                    employee_ids.append(employee_id)
        self.check_schedule_leaves(employee_ids)

    def create_attendance(self, employee_id, contract_id, dates, calendar_id):
        self.ensure_one()
        # PreApprChecks = self.env['pre.approved.checks.day']
        if len(dates) == 1:
            self.create_incidence(employee_id, dates[0])
            return

        tolerance = 0
        if contract_id.tolerance == 'restrictive':
            tolerance = abs(contract_id.tolerance_time)

        check_in = self.get_date_str(dates[0])
        end_date = self.get_date_str(dates[1])

        attendance_dict = {
            'employee_id': employee_id.id,
            'check_in': check_in,
            'schedule_delay': calendar_id.get_check_in_incidences(check_in, tolerance)
        }

        # approved_checks = PreApprChecks.search([
        #     ('employee_id', '=', employee_id.id),
        #     ('date', '=', dates[0].date())
        # ])

        # if len(approved_checks) > 0:
        #     attendance_dict['check_out'] = end_date
        #     attendance = self.env['hr.attendance'].with_context(approve_incidence=True).create(attendance_dict)
        # else:
        attendance = self.env['hr.attendance'].with_context(approve_incidence=True).create(attendance_dict)

        ranges = calendar_id.get_ranges_of_working_time(attendance.check_in, end_date, attendance, tolerance)
        if ranges:
            attendance = ranges['working']
            incidences = ranges['incidences']
            employee_id.with_context(approve_incidence=True).write({'attendance_ids': attendance, 'incidence_ids': incidences})

        del(dates[0])
        del(dates[0])

        if len(dates):
            self.create_attendance(employee_id, contract_id, dates, calendar_id)

    def create_incidence(self, employee_id, date):
        self.ensure_one()
        self.env['attendance.incidence'].create({
            'name': 'Only one log date',
            'type_incidence': 'incomplete_logs',
            'employee_id': employee_id.id,
            'check_in': self.get_date_str(date),
            'is_computed': True
        })

    def _unlink_object(self, Object):
        self.ensure_one()
        search = [
            ('period_id', '=', self.period_id.id),
            ('employee_id', 'in', self.employee_ids.ids)
        ]
        if self.search_date:
            search.append(('date_computed', '=', self.search_date))
        Object.search(search).unlink()

    def _unlink_attendance_by_employees(self):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        self._unlink_object(Attendance)

    def _unlink_incidence_by_employees(self):
        self.ensure_one()
        EmpIncidence = self.env['attendance.incidence']
        self._unlink_object(EmpIncidence)

    def _unlink_origin_attendance_by_employees(self):
        self.ensure_one()
        OrigAtt = self.env['original.attendance']
        self._unlink_object(OrigAtt)

    def _unlink_computed_objects_by_employees(self):
        self.ensure_one()
        self._unlink_attendance_by_employees()
        self._unlink_incidence_by_employees()
        self._unlink_origin_attendance_by_employees()

    def check_schedule_leaves(self, employee_ids):
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Incidence = self.env['attendance.incidence']
        for employee_id in employee_ids:
            Attendance.search([
                ('employee_id', '=', employee_id.id),
                ('period_id', '=', self.period_id.id)
            ]).check_schedule_leaves()
            Incidence.search([
                ('employee_id', '=', employee_id.id),
                ('period_id', '=', self.period_id.id)
            ]).check_schedule_leaves()
