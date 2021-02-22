# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import models, fields, api


class HrContractActions(models.TransientModel):
    _name = 'hr.contract.actions'
    _description = 'hr.contract.actions'

    structure_type_id = fields.Many2one('hr.payroll.structure.type', 'Salary Structure Type')
    resource_calendar_id = fields.Many2one('resource.calendar', 'Working Schedule')
    period_group_id = fields.Many2one('payment.period.group', 'Payment Period Groups')
    employee_ids = fields.One2many('temporal.employee.line', 'contract_action_id')
    contract_ids = fields.One2many('temporal.contract.line', 'contract_action_id')
    workcenter_ids = fields.One2many('temporal.workcenter.line', 'contract_action_id')

    @api.model
    def default_get(self, fields):
        res = super(HrContractActions, self).default_get(fields)
        context = self._context
        ids = context.get('active_ids', [])
        if context.get('source_model_tmp') == 'hr.contract':
            _ids = [self.env['temporal.contract.line'].create({'contract_id': contract_id}).id for contract_id in ids]
            res['contract_ids'] = _ids
            _ids = [self.env['temporal.workcenter.line'].create({'contract_id': contract_id}).id for contract_id in ids]
            res['workcenter_ids'] = _ids
        elif context.get('source_model_tmp') == 'hr.employee':
            _ids = [self.env['temporal.employee.line'].create({'employee_id': employee_id}).id for employee_id in ids]
            res['employee_ids'] = _ids
        return res

    def generate_contracts(self):
        self.ensure_one()
        HrContract = self.env['hr.contract']
        for employee in self.employee_ids:
            HrContract.create(self._get_new_contract_dict(employee))

    def assign_period_group_button(self):
        self.ensure_one()
        HrContract = self.env['hr.contract']
        if self.employee_ids and len(self.employee_ids) > 0:
            for employee_id in self.employee_ids:
                contract_id = HrContract.search([('employee_id', '=', employee_id.id)], limit=1)
                contract_id.period_group_id = self.period_group_id.id
        else:
            for contract_id in self.contract_ids.mapped('contract_id'):
                contract_id.period_group_id = self.period_group_id.id

    def assign_workcenter_button(self):
        self.ensure_one()
        for _id in self.workcenter_ids:
            _id.workcenter_id.contract_id = _id.contract_id.id

    def _get_new_contract_dict(self, employee_id):
        self.ensure_one()
        return {
            'name': 'Contrato {0}'.format(employee_id.name.strip()),
            'employee_id': employee_id.id,
            'type_id': self.type_id.id,
            'resource_calendar_id': self.resource_calendar_id.id,
            'wage': 0,
            'period_group_id': self.period_group_id.id
        }

class TemporalEmployeeLine(models.TransientModel):
    _name = 'temporal.employee.line'
    _description = 'temporal.employee.line'

    contract_action_id = fields.Many2one('hr.contract.actions')
    employee_id = fields.Many2one('hr.employee')

class TemporalContractLine(models.TransientModel):
    _name = 'temporal.contract.line'
    _description = 'temporal.contract.line'

    contract_action_id = fields.Many2one('hr.contract.actions')
    contract_id = fields.Many2one('hr.contract')

class TemporalWorkcenterLine(models.TransientModel):
    _name = 'temporal.workcenter.line'
    _description = 'temporal.workcenter.line'

    contract_action_id = fields.Many2one('hr.contract.actions')
    workcenter_id = fields.Many2one('mrp.workcenter')
    contract_id = fields.Many2one('hr.contract')