# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PackageWizard(models.TransientModel):
    _name = 'package.wizard'
    _description = 'package.wizard'

    product_tmpl_id = fields.Many2one('product.template', string='Package')

    def create_lines(self):
        self.ensure_one()
        Sale = self.env['sale.order']
        SalePackage = self.env['sale.order.package']
        Product = self.env['product.product']

        context = self.env.context
        active_ids = context.get('active_ids')
        order_ids = Sale.browse(active_ids)

        for order_id in order_ids:

            line_ids = []
            for item in self.product_tmpl_id.package_ids:
                default_product_id = Product.search([('categ_id', '=', item.categ_id.id)], limit=1)
                if default_product_id:
                    for qty in range(0, item.quantity):
                        line_ids.append((0, False, {'package_categ_id': item.categ_id.id,
                                                    'order_id': order_id.id,
                                                    'product_id': default_product_id.id,
                                                    'is_required': item.is_required}))

            SalePackage.create({'product_tmpl_id': self.product_tmpl_id.id,
                                'order_id': order_id.id,
                                'line_ids': line_ids})


class PackageProductWizard(models.TransientModel):
    _name = 'package.product.wizard'
    _description = 'package.product.wizard'

    categ_id = fields.Many2one('product.category')
    product_id = fields.Many2one('product.product')

    def change_product(self):
        self.ensure_one()
        SaleLine = self.env['sale.order.line']

        context = self.env.context
        active_ids = context.get('active_ids')
        order_line_ids = SaleLine.browse(active_ids)

        for order_line_id in order_line_ids:
            order_line_id.product_id = self.product_id.id
            order_line_id.product_id_change()
