# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_package = fields.Boolean(related='product_tmpl_id.is_package', store=True)

    @api.model
    def _ikom_set_settings(self):
        """
            Creating required products, serial numbers and stock moves to enable a quick testing, we are assuming
            that we are working with an empty database, remove demo.xml on the manifest to avoid creating this
            products.
        """
        Category = self.env['product.category']
        Template = self.env['product.template']
        Serial = self.env['stock.production.lot']
        Pricelist = self.env['product.pricelist']
        PricelistItem = self.env['product.pricelist.item']
        Stock = self.env['stock.quant']
        Location = self.env['stock.location']

        categ_package = Category.search([('name', '=', 'Package')], limit=1)
        categ_phone = Category.search([('name', '=', 'Phone')], limit=1)
        categ_protection = Category.search([('name', '=', 'Protection')], limit=1)
        categ_plan = Category.search([('name', '=', 'Plan')], limit=1)

        pricelist_id = Pricelist.search([], limit=1)
        location_id = Location.search([('usage', '=', 'internal')], limit=1)

        #   Packages
        # Creating the 3 types of packages
        if not Template.search([('name', '=', 'Prepaid Sale')]):
            Template.create({'name': 'Prepaid Sale', 'categ_id': categ_package.id,
                             'package_ids': [(0, False, {'categ_id': categ_phone.id, 'quantity': 1})]})
            Template.create({'name': 'Plan Sale', 'categ_id': categ_package.id,
                             'package_ids': [(0, False, {'categ_id': categ_plan.id, 'quantity': 1})]})
            Template.create({'name': 'Activation Sale', 'categ_id': categ_package.id,
                             'package_ids': [(0, False, {'categ_id': categ_phone.id, 'quantity': 1}),
                                             (0, False, {'categ_id': categ_plan.id, 'quantity': 1}),
                                             (0, False, {'categ_id': categ_protection.id, 'quantity': 1,
                                                         'is_required': False})]})

        #     Services
        for variant_id in self.search([('categ_id', 'in', [categ_protection.id, categ_plan.id])]):
            values = variant_id.product_template_attribute_value_ids
            values = [int(r.name) for r in values.product_attribute_value_id if r.name.isnumeric()]
            if not PricelistItem.search([('pricelist_id', '=', pricelist_id.id),
                                  ('product_id', '=', variant_id.id)]):
                PricelistItem.create({'pricelist_id': pricelist_id.id,
                                      'product_tmpl_id': variant_id.product_tmpl_id.id,
                                      'product_id': variant_id.id,
                                      'fixed_price': sum(values)})

        #     Phones
        for variant_id in self.search([('categ_id', '=', categ_phone.id)]):

            # This is just to give a different price on each product
            if 'M3' in variant_id.name:
                product_value = 3000
            else:
                product_value = 5000

            values = variant_id.product_template_attribute_value_ids
            values = [r.name.lower() for r in values.product_attribute_value_id]
            'Black is 100 MXN more'
            if 'black' in values:
                product_value += 100

            if '128 GB' in values:
                product_value += 500

            if not PricelistItem.search([('pricelist_id', '=', pricelist_id.id),
                                         ('product_id', '=', variant_id.id)]):
                PricelistItem.create({'pricelist_id': pricelist_id.id,
                                      'product_tmpl_id': variant_id.product_tmpl_id.id,
                                      'product_id': variant_id.id,
                                      'fixed_price': product_value})

            serial_id = Serial.create({'product_id': variant_id.id, 'company_id': self.env.company.id})
            Stock.create({'product_id': variant_id.id,
                          'lot_id': serial_id.id,
                          'location_id': location_id.id,
                          'quantity': 1})
