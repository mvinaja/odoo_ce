# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CreateProductAttributeValueWizard(models.TransientModel):
    _name = 'create.product.attribute.value.wizard'
    _description = 'Create Sequencial Attribute Values'

    prefix = fields.Char('Prefix')
    suffix = fields.Char('Suffix')
    digits = fields.Integer('Digits', default=2)

    attribute_id = fields.Many2one('product.attribute')
    quantity = fields.Integer('Quantity', default=1)
    code_length = fields.Integer(default=4)
    sequence_start = fields.Integer('Start From', default=5)
    sequence_increment = fields.Integer('Increment By', default=5)

    def create_value_btn(self):
        AttributeValue = self.env['product.attribute.value']

        new_values = AttributeValue
        for indx in range(self.quantity):
            sequence = indx * self.sequence_increment + self.sequence_start

            prefix = self.prefix or ''
            suffix = self.suffix or ''
            code = str(sequence).rjust(self.digits, '0')
            new_values += AttributeValue.create({
                'attribute_id': self.attribute_id.id,
                'name': '{}{}{}'.format(prefix, code, suffix),
                'code_length': self.code_length
            })
        action = self.env.ref('aci_product.product_attribute_value_action').read()[0]
        action['domain'] = [('id', 'in', new_values.ids)]
        return action
