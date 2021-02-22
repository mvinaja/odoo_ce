# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    tracking_password = fields.Char(default='')
    analytic_account_id = fields.Many2one('account.analytic.account')
    valid_employee = fields.Boolean()
    code = fields.Char()
    block_ids = fields.One2many('hr.productivity.block', 'employee_id')


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    incidence_ids = fields.One2many('attendance.incidence', 'employee_id')
    tracking_password = fields.Char(default='', invisible=True, copy=False,
                                    help="Keep empty if you don't want the user to be able to connect on the system.")
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', ondelete='restrict')
    valid_employee = fields.Boolean(compute='_compute_valid_employee', store=True, help='Employee has Workcenter')
    code = fields.Char()
    block_ids = fields.One2many('hr.productivity.block', 'employee_id')

    @api.depends('contract_ids', 'child_ids')
    def _compute_valid_employee(self):
        for r in self:
            valid = False
            contract_id = self.env['hr.contract'].search([('state', '=', 'open'),
                                                          ('employee_id', '=', r.id)])
            if contract_id and contract_id.workcenter_ids and r.child_ids:
                valid = True
            r.valid_employee = valid

    @api.depends('attendance_ids')
    def _compute_last_attendance_id(self):
        for employee in self:
            employee.last_attendance_id = employee.attendance_ids and employee.attendance_ids[0] or False
            for attendance in employee.attendance_ids:
                if attendance.check_out is False:
                    employee.last_attendance_id = attendance.id

    def attendance_action(self, next_action):
        """ Changes the attendance of the employee.
            Returns an action to the check in/out message,
            next_action defines which menu the check in/out message should return to. ("My Attendances" or "Kiosk Mode")
        """
        self.ensure_one()
        action_message = self.env.ref('hr_attendance.hr_attendance_action_greeting_message').read()[0]
        action_message['previous_attendance_change_date'] = self.last_attendance_id and (self.last_attendance_id.check_out or self.last_attendance_id.check_in) or False
        action_message['employee_name'] = self.name
        action_message['next_action'] = next_action

        if self.user_id:
            modified_attendance = self.sudo(self.user_id.id).attendance_action_change()
        else:
            modified_attendance = self.sudo().attendance_action_change()

        # Add id for validation
        id_att = modified_attendance.id
        # Add for check schedule leaves on attendance and incidence
        self.incidence_ids.check_schedule_leaves()
        self.attendance_ids.check_schedule_leaves()

        # Add validation
        if self.env['hr.attendance'].search([('id', '=', id_att)], limit=1):
            action_message['attendance'] = modified_attendance.read()[0]
        return {'action': action_message}

    def attendance_action_change(self):
        """ Check In/Check Out action
            Check In: create a new attendance record
            Check Out: modify check_out field of appropriate attendance record
        """
        if len(self) > 1:
            raise UserError(_('Cannot perform check in or check out on multiple employees.'))
        action_date = fields.Datetime.now()

        Contract = self.env['hr.contract']
        contract_id = Contract.search([('employee_id', '=', self.id)], limit=1)
        if contract_id:
            calendar_id = contract_id.resource_calendar_id

        if self.attendance_state != 'checked_in':
            if contract_id and calendar_id and contract_id.tolerance != 'open':
                vals = self.check_schedule_check_in_employee(action_date, contract_id, calendar_id)
            else:
                vals = {
                    'employee_id': self.id,
                    'check_in': action_date,
                }
            return self.env['hr.attendance'].create(vals)
        else:
            attendance = self.env['hr.attendance'].search([('employee_id', '=', self.id), ('check_out', '=', False)], limit=1)
            if attendance:
                attendance.check_out = action_date
                if contract_id and calendar_id and contract_id.tolerance != 'open':
                    self.check_schedule_for_employee(attendance, action_date, contract_id, calendar_id)
                else:
                    attendance.check_out = action_date
            else:
                raise UserError(_('Cannot perform check out on %(empl_name)s, could not find corresponding check in. '
                    'Your attendances have probably been modified manually by human resources.') % {'empl_name': self.name, })
            return attendance

    def check_schedule_for_employee(self, attendance, action_date, contract_id, calendar_id):
        self.ensure_one()
        if attendance.incidence_id:
            attendance.incidence_id.check_out = action_date
            attendance.check_out = attendance.check_in
            attendance.check_schedule_leaves()
        else:
            tolerance = 0
            if contract_id.tolerance == 'restrictive':
                tolerance = abs(contract_id.tolerance_time)
            ranges = calendar_id.get_ranges_of_working_time(attendance.check_in, action_date, attendance, tolerance)
            incidences = ranges['incidences']
            attendance = ranges['working']
            self.write({'attendance_ids': attendance, 'incidence_ids': incidences})

    def check_schedule_check_in_employee(self, check_in, contract_id, calendar_id):
        self.ensure_one()
        tolerance = 0
        if contract_id.tolerance == 'restrictive':
            tolerance = abs(contract_id.tolerance_time)

        attendance = {
            'employee_id': self.id,
            'check_in': check_in,
        }
        if calendar_id.get_check_in_incidences(check_in, tolerance):
            attendance['schedule_delay'] = True

        return attendance

