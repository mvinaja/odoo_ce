# -*- coding: utf-8 -*-

from odoo import api, models, fields


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _default_structure(self):
        return self.env['ir.model.data'].get_object(
            'hr_payroll', 'structure_base')

    period_group_id = fields.Many2one('payment.period.group')
    tolerance = fields.Selection([
        ('restrictive', 'Restrictive'),
        ('open', 'Open')
    ], default='restrictive')
    tolerance_time = fields.Float('Tolerance Minutes', default=15)
    modify_delay = fields.Boolean('Modify Delay', default=False)
    workcenter_id = fields.Many2one('mrp.workcenter', domain="[('resource_type', '=', 'alternative')]")
    workcenter_ids = fields.One2many('mrp.workcenter', 'contract_id', string='Workcenters')

    @api.depends('department_id')
    def _compute_department_ids(self):
        for r in self:
            for _id in self._recursive_department(r.department_id.id):
                department_ids = self._recursive_department(_id)
        return department_ids.append(r.department_id.id)

    def _recursive_department(self, department_id):
        return self.env['hr.department'].search([('parent_id', '=', department_id)]).ids
