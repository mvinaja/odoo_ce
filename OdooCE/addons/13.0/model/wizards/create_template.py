# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CreateProductTemplateWizard(models.TransientModel):
    _name = 'create.product.template.wizard'
    _description = 'Create Sequencial Product Templates'

    @api.model
    def _default_uom(self):
        return self.env.ref('uom.product_uom_unit').id

    quantity = fields.Integer('Quantity', default=1)
    prefix = fields.Char('Prefix')
    suffix = fields.Char('Suffix')

    code_start = fields.Integer('Code Start', default=5)
    code_increment = fields.Integer('Code Increment', default=5)
    code_digits = fields.Integer('Code Digits', default=2)

    sequence_start = fields.Integer('Start From', default=10000)
    sequence_increment = fields.Integer('Increment By', default=50)

    type = fields.Selection([
        ('consu', 'Consumable'),
        ('service', 'Service'),
        ('product', 'Product')
    ], default='product')
    category_id = fields.Many2one('product.category')
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure', default=_default_uom)
    uom_po_id = fields.Many2one('uom.uom', 'Purchase UoM.', default=_default_uom)
    standard_price = fields.Float(default=0)

    def create_template_btn(self):
        ProductTemplate = self.env['product.template']

        new_templates = ProductTemplate
        for indx in range(self.quantity):
            sequence = indx * self.sequence_increment + self.sequence_start
            code = indx * self.code_increment + self.code_start

            prefix = self.prefix or ''
            suffix = self.suffix or ''
            new_templates += ProductTemplate.create({
                'sequence': sequence,
                'name': '{}{}{}'.format(prefix, code, suffix),
                'config_ok': True,
                'categ_id': self.category_id.id,
                'type': self.type,
                'uom_id': self.uom_id.id,
                'uom_po_id': self.uom_po_id.id,
                'tracking': 'none',
                'standard_price': self.standard_price

            })
        action = self.env.ref('product.product_template_action').read()[0]
        action['domain'] = [('id', 'in', new_templates.ids)]
        return action
