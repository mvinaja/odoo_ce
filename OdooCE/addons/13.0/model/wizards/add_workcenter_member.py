# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AddWorkcenterMemberWizard(models.TransientModel):
    _name = 'add.workcenter.member.wizard'
    _description = 'add.workcenter.member.wizard'

    workcen_id = fields.Many2one('mrp.workcenter', 'Workcenter')

    def add_member_btn(self):
        context = self.env.context
        ModelData = self.env['ir.model.data']
        Product = self.env['product.product']
        WorkcenMember = self.env['mrp.workcenter.member']

        # Browse selected products
        selected_products = Product.browse(context.get('active_ids'))

        # Add new members
        for product_id in selected_products:
            WorkcenMember.create({
                'workcen_id': self.workcen_id.id,
                'product_id': product_id.id,
                'quantity': 1
            })

        view_id = ModelData.get_object(
            'mrp', 'mrp_workcenter_view')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'res_model': 'mrp.workcenter',
            'res_id': self.workcen_id.id,
            'target': 'current'
        }
