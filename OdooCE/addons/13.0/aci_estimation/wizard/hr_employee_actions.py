# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import models, fields, api


class HrEmployeeActions(models.TransientModel):
    _name = 'hr.employee.actions'
    _description = 'hr.employee.actions'

    employee_ids = fields.Many2many('hr.employee', string='Employees')
    create_project = fields.Boolean('Create Analytic', default=True)
    project_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    resource_calendar_id = fields.Many2one('resource.calendar', 'Working Schedule', required=True)
    structure_type_id = fields.Many2one('hr.payroll.structure.type', 'Salary Structure Type', required=True)
    date_start = fields.Datetime('Date Start', required=True, default=datetime.now())

    currency_id = fields.Many2one('res.currency', string='Currency')
    wage = fields.Monetary('Wage', digits=(16, 2), required=True, help="Employee's monthly gross wage.")
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('pending', 'To Renew'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', help='Status of the contract', default='draft')
    tolerance = fields.Selection([
        ('restrictive', 'Restrictive'),
        ('open', 'Open')
    ], default='restrictive')
    tolerance_time = fields.Float('Tolerance Minutes', default=15)
    period_group_id = fields.Many2one('payment.period.group', 'Period Group')

    @api.model
    def default_get(self, fields):
        res = super(HrEmployeeActions, self).default_get(fields)
        context = self._context
        ids = context.get('active_ids', [])
        res['employee_ids'] = ids
        return res

    def create_contract_btn(self):
        for employee_id in self.employee_ids:
            project_id = self.project_id if not self.create_project else self.env['account.analytic.account'].create({'name': employee_id.name})
            self.env['hr.contract'].create({
                'name': employee_id.name,
                'employee_id': employee_id.id,
                'analytic_account_id': project_id.id,
                'date_start': self.date_start,
                'resource_calendar_id': self.resource_calendar_id.id,
                'tolerance': self.tolerance,
                'tolerance_time': self.tolerance_time,
                'wage': self.wage,
                'type_id': self.type_id.id,
                'period_group_id': self.period_group_id.id
            })
