# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    def show_workcenter_btn(self, context=None):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Workcenters',
            'view_type': 'form',
            'view_mode': 'tree, form',
            'res_model': 'mrp.workcenter',
            'views': [[False, "tree"]],
            'domain': [('department_id', '=', self.id)],
            'target': 'current',
        }