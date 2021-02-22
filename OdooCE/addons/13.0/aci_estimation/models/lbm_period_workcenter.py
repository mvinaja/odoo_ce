# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class LbmPeriodWorkcenter(models.Model):
    _inherit = 'lbm.period.workcenter'

    contract_id = fields.Many2one(related='workcenter_id.contract_id')

    def show_assign_section_btn(self):
        timetracking_ids = self.env['mrp.timetracking'].search([('workcenter_id', '=', self.workcenter_id.id),
                                                            ('baseline_id', '=', self.period_id.scenario_id.baseline_id.id),
                                                            ('date_start', '>=', self.period_id.period_id.from_date),
                                                            ('date_start', '<=', self.period_id.period_id.to_date)])
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'name': 'Activity',
            'res_model': 'mrp.timetracking',
            'target': 'current',
            'domain': [('id', 'in', timetracking_ids.ids)],
            "context": {'search_default_active_stage': 1}
        }

    def button_estimate_block(self, context=None):
        estimation_ids = self.env['mrp.estimation'].search([('workcenter_id', '=', self.workcenter_id.id),
                                                            ('start_period', '>=', self.period_id.period_id.from_date),
                                                            ('start_period', '<=', self.period_id.period_id.to_date)])

        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree'), (False, 'form')],
            'view_mode': 'tree',
            'name': 'Estimations',
            'res_model': 'mrp.estimation',
            'target': 'current',
            'context': {'default_workcenter_id': self.workcenter_id.id,
                        'search_default_filter_active_estimation': 1},
            'domain': [('id', '=', estimation_ids.ids)]
        }
