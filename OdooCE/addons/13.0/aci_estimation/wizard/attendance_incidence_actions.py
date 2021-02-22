# -*- coding: utf-8 -*-

from odoo import models, fields, api
from collections import namedtuple
from datetime import datetime
from datetime import timedelta

from odoo.exceptions import ValidationError

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class AttendanceIncidenceActions(models.TransientModel):
    _name = 'attendance.incidence.actions'
    _description = 'attendance.incidence.actions'

    employee_ids = fields.Many2many('hr.employee', 'attendance_incidence_actions__hr_employee',
        'attendance_incidence_actions', 'employee_id', string='Employees')
    check_in = fields.Datetime('Check In')
    check_out = fields.Datetime('Check Out')

    description = fields.Text()
    approve = fields.Boolean('Approve', default=False)
    productivity_block = fields.Boolean(string='Create Block', default=False)

    def _get_incidence(self):
        incidences = [('leave', 'Leave Not Payable'), ('omission', 'Worker Omission')]
        if self.env.user.has_group('aci_estimation.group_timetracking_supervisor'):
            incidences.append(('work_not_payable', 'Work Not Payable'))
            incidences.append(('holiday', 'Holiday Payable by Law'))
            incidences.append(('holiday_company', 'Holiday Payable by Company'))
            incidences.append(('paid_holiday', 'Paid Holiday by Law'))
            incidences.append(('paid_holiday_company', 'Paid Holiday by Company'))
        return incidences

    type_incidence = fields.Selection(_get_incidence, 'Type', required=True, default='leave')

    def generate_incidences(self):
        self.ensure_one()
        EmpIncidence = self.env['attendance.incidence']

        for employee_id in self.employee_ids:

            if self.productivity_block:
                contract_id = self.env['hr.contract'].search([('employee_id', '=', employee_id.id),
                                                              ('state', 'in', ['open', 'pending'])], limit=1)

                if not contract_id:
                    raise ValidationError("{} does not have a running contract.".format(employee_id.name))

                check_in = self.check_in
                check_out = self.check_out
                user_id = employee_id.user_id if employee_id.user_id else self.env.user
                incidence_start = self.env['time.tracking.actions'].get_tz_datetime(check_in, user_id)
                incidence_end = self.env['time.tracking.actions'].get_tz_datetime(check_out, user_id)
                delta = incidence_end - incidence_start  # as timedelta

                for day in range(delta.days + 1):
                    date = incidence_start + timedelta(days=day)
                    attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                        .filtered(lambda r: int(r.dayofweek) == int(date.weekday()))

                    if attendance_ids:
                        day_start = attendance_ids.sorted(lambda r: r.hour_from)[0]
                        day_end = attendance_ids.sorted(lambda r: r.hour_to, reverse=True)[0]

                        from_hour = int('{0:02.0f}'.format(*divmod(day_start.hour_from * 60, 60)))
                        from_minutes = int('{1:02.0f}'.format(*divmod(day_start.hour_from * 60, 60)))
                        to_hour = int('{0:02.0f}'.format(*divmod(day_end.hour_to * 60, 60)))
                        to_minutes = int('{1:02.0f}'.format(*divmod(day_end.hour_to * 60, 60)))

                        day_start = date.replace(hour=from_hour, minute=from_minutes, second=0)
                        day_end = date.replace(hour=to_hour, minute=to_minutes, second=0)

                        if day == 0:
                            incidence_final_start = incidence_start if incidence_start > day_start else day_start
                        else:
                            incidence_final_start = day_start
                        incidence_final_end = incidence_end if incidence_end < day_end else day_end

                        final_start = self.env['time.tracking.actions'].remove_tz_datetime(incidence_final_start,
                                                                                           employee_id.user_id)
                        final_end = self.env['time.tracking.actions'].remove_tz_datetime(incidence_final_end,
                                                                                           employee_id.user_id)
                        EmpIncidence.create({
                            'employee_id': employee_id.id,
                            'name': self.description,
                            'check_in': final_start,
                            'check_out': final_end,
                            'type_incidence': self.type_incidence,
                            'approve': False,
                            'productivity_block': self.productivity_block
                        })
            else:
                EmpIncidence.create({
                    'employee_id': employee_id.id,
                    'name': self.description,
                    'check_in': self.check_in,
                    'check_out': self.check_out,
                    'type_incidence': self.type_incidence,
                    'approve': False,
                    'productivity_block': self.productivity_block
                })
        # return {
        #     'type': 'ir.actions.client',
        #     'tag': 'reload',
        # }

    def approve_incidence_button(self):
        self.ensure_one()
        EmployeeIncidence = self.env['attendance.incidence']
        context = self.env.context
        active_ids = context.get('active_ids')
        incidence_ids = EmployeeIncidence.browse(active_ids)
        for incidence_id in incidence_ids:
            approved_incidence_ids = EmployeeIncidence.search([('employee_id', '=', incidence_id.employee_id.id),
                                                               ('state', '=', 'approved')])
            for approved_incidence_id in approved_incidence_ids:
                if self.overlap_days(approved_incidence_id.check_in, approved_incidence_id.check_out,
                                     incidence_id.check_in, incidence_id.check_out) > 0:
                    raise ValidationError("The approved incidences overlaps with one of the draft incidences")

        incidence_ids.filtered(lambda r: r.check_in and r.check_out and r.state == 'draft').approve_incidence()
        # EmployeeIncidence.browse(active_ids).filtered(lambda r: r.check_in and r.check_out)\
        #     .write({'approve': context.get('approve')})


    def overlap_days(self, start1, end1, start2, end2):
        Range = namedtuple('Range', ['start', 'end'])
        r1 = Range(start=start1,
                   end=end1)
        r2 = Range(start=start2,
                   end=end2)
        latest_start = max(r1.start, r2.start)
        earliest_end = min(r1.end, r2.end)
        delta = (earliest_end - latest_start).days + 1 if latest_start != earliest_end else 0
        return max(0, delta)

    def reject_incidence_button(self):
        self.ensure_one()
        EmployeeIncidence = self.env['attendance.incidence']
        context = self.env.context
        active_ids = context.get('active_ids')
        EmployeeIncidence.browse(active_ids)\
            .filtered(lambda r: r.check_in and r.check_out and r.state == 'draft').reject_incidence()

    def send_to_draft_incidence_button(self):
        self.ensure_one()
        EmployeeIncidence = self.env['attendance.incidence']
        context = self.env.context
        active_ids = context.get('active_ids')
        EmployeeIncidence.browse(active_ids)\
            .filtered(lambda r: r.check_in and r.check_out and r.state in ['approved', 'rejected']).send_to_draft_incidence()

    def adjust_massively_log_dates_button(self):
        self.ensure_one()
        EmployeeIncidence = self.env['attendance.incidence']
        context = self.env.context
        active_ids = context.get('active_ids')

        dict_write = {}
        if self.check_in:
            dict_write['check_in'] = self.check_in
        if self.check_out:
            dict_write['check_out'] = self.check_out

        EmployeeIncidence.browse(active_ids).write(dict_write)
