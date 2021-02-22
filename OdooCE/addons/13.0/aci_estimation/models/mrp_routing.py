# -*- coding: utf-8 -*-
from odoo import models, api, fields, _

class MrpRouting(models.Model):
    _inherit = 'mrp.routing'

    def action_mrp_workorder_show_steps(self):
        self.ensure_one()
        picking_type_id = self.env['stock.picking.type'].search([('code', '=', 'mrp_operation')], limit=1).id
        action = self.env.ref('mrp_workorder.action_mrp_workorder_show_steps').read()[0]
        ctx = dict(self._context, default_picking_type_id=picking_type_id, default_company_id=self.company_id.id)
        action.update({'context': ctx})
        return action

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        routing_ids = super(MrpRouting, self).search(
            args=args, offset=offset, limit=limit, order=order, count=count)
        warehouse_id = self.env.user.get_context_warehouse()
        bom_ids = self.env['mrp.bom'].search([('context_warehouse', '=', warehouse_id.id)])
        return routing_ids | bom_ids.routing_id