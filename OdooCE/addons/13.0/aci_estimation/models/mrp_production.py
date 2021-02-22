# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    supervisor_ids = fields.Many2many('hr.employee', 'mrp_production_supervisor_rel', 'production_id', 'employee_id')
    type = fields.Selection(selection_add=[('periodic', 'Periodic Goals')], ondelete={'periodic': 'cascade'})
    workorder_count = fields.Integer('# Work Orders', compute='_compute_workorder_count')

    def compute_workcenter_btn(self, context=None):
        TimeTracking = self.env['mrp.timetracking']
        for scenario_id in self.env['lbm.scenario'].search([]).filtered(lambda r: r.planning_type == 'replanning'):
            for production_id in scenario_id.baseline_id.production_ids:
                workcenter_ids = production_id.workorder_ids.mapped('resource_id').ids
                TimeTracking.create_estimation_workcenter(workcenter_ids)

    def delete_tracking_btn(self):
        todo_stage_id = self.env['time.tracking.actions'].get_stage_id('ToDo')
        self.env['mrp.workcenter.productivity'].search([('workorder_id', 'in', self.workorder_ids.ids)]).unlink()
        self.env['mrp.timetracking'].search([('production_id', '=', self.id)]).write({'stage_id': todo_stage_id})

    @api.depends('workorder_ids')
    def _compute_workorder_count(self):
        for production in self:
            production.workorder_count = len(production.workorder_ids)

    def unlink(self):
        for r in self:
            if r.id in self.env['lbm.scenario'].search([('planning_type', '=', 'replanning')]).baseline_id.production_ids.ids:
                raise ValidationError(_('Cannot remove a Manufacturing Order that belongs to an replanning scenario'))
        super(MrpProduction, self).unlink()
