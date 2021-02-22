# -*- coding: utf-8 -*-

from odoo import models, fields, api,_
import datetime


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    def show_period_estimation(self):
        context = self.env.context
        workcenter_ids = context.get('workcenter_ids') if context.get('workcenter_ids') else []
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_tree_view')

        production_ids = self.env['mrp.production'].search([('context_warehouse', '=', self.id)]).ids
        wo_ids = self.env['mrp.workorder'].search([('production_id', 'in', production_ids)]).mapped('resource_id')
        step_ids = self.env['lbm.work.order.step'].search([('production_id', 'in', production_ids)]).mapped('wkcenter')
        record_ids = wo_ids.ids + step_ids.ids
        _workcenter_ids = list(set(record_ids) & set(workcenter_ids))

        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree'), (False, 'form')],
            'view_mode': 'tree, form',
            'target': 'current',
            'name': _('Estimation'),
            'res_model': 'mrp.estimation',
            'domain': [('workcenter_id', 'in', _workcenter_ids)],
            'context': {'warehouse_id': self.id,
                        'search_default_filter_periodic_estimation': 1}
        }

    def show_restriction(self):
        return self.show_activity_type('restriction')

    def show_noncompliance(self):
        return self.show_activity_type('noncompliance')

    def show_nonconformity(self):
        return self.show_activity_type('nonconformity')

    def show_activity_type(self, activity_source):
        context = self.env.context
        workcenter_ids = context.get('workcenter_ids') if context.get('workcenter_ids') else []
        production_ids = self.env['mrp.production'].search([('context_warehouse', '=', self.id)])
        activity_ids = []
        for activity in production_ids.mapped('workorder_ids').activity_ids.\
            filtered(lambda r: r.activity_source == activity_source):
            if self.env.user.has_group('aci_estimation.group_estimation_chief'):
                activity_ids.append(activity.id)
            elif list(set(activity.workcenter_ids) & set(workcenter_ids)):
                activity_ids.append(activity.id)

        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mail_activity_tree_view')
        return {
            'name': _('Restrictions'),
            'res_model': 'mail.activity',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree')],
            'target': 'current',
            'domain': [('id', 'in', activity_ids)],
            'context': self._context,
        }

    def show_workcenter_estimation(self):
        context = self.env.context
        workcenter_ids = context.get('workcenter_ids') if context.get('workcenter_ids') else []
        parent_workcenter_id = context.get('parent_workcenter_id') if context.get('parent_workcenter_id') else None
        est_workcenter_ids = context.get('est_workcenter_ids') if context.get('est_workcenter_ids') else []
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_workcenter_tree_view')

        production_ids = self.env['mrp.production'].search([('context_warehouse', '=', self.id)]).ids
        wo_ids = self.env['mrp.workorder'].search([('production_id', 'in', production_ids)]).mapped('resource_id')
        step_ids = self.env['lbm.work.order.step'].search([('production_id', 'in', production_ids)]).mapped('wkcenter')
        record_ids = wo_ids.ids + step_ids.ids

        _ids = self.env['mrp.estimation.workcenter'].search([('workcenter_id', 'in', record_ids)]).ids
        _workcenter_ids = list(set(_ids) & set(est_workcenter_ids))
        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree')],
            'view_mode': 'tree',
            'target': 'current',
            'name': _('Workcenter'),
            'res_model': 'mrp.estimation.workcenter',
            'domain': [('id', 'in', _workcenter_ids)],
            'context': {'search_default_filter_active_estimation': 1,
                        'workcenter_ids': workcenter_ids,
                        'parent_workcenter_id': parent_workcenter_id,
                        'warehouse_id': self.id}
        }
        return action