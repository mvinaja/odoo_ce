# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from odoo.exceptions import ValidationError as Alert
import itertools


class CreateProductWizard(models.TransientModel):
    _name = 'create.product.wizard'
    _description = 'Create Product Wizard'

    type = fields.Selection([
        ('any', 'All'),
        ('budget', 'Budget'),
        ('phase', 'Phase'),
        ('model', 'Model'),
        ('workorder', 'Workorder'),
        ('basic', 'Basic'),
        ('normal', 'Simple'),
        ('labor', 'Crew & Labor'),
        ('party', 'Party')
    ], 'Product Type', default='any')

    source_category = fields.Many2one('product.attribute.category', 'Source')
    source_attribute = fields.Many2one('product.attribute', 'Attrib.')
    source_selection = fields.Many2many(
        'product.attribute.value', 'create_product_wizard__source_selection')
    source_values = fields.Many2many(
        'product.attribute.value', 'create_product_wizard__source_values', string='Values')

    source_templates = fields.Many2many(
        'product.template', 'create_product_wizard__source_templates', string='Templates')
    target_products = fields.Many2many(
        'product.product', 'create_product_wizard__target_products', string='Products')
    virtual_products = fields.One2many('create.product.wizard.line', 'wizard_id')

    bom_count = fields.Integer(compute='_compute_count')
    product_count = fields.Integer(compute='_compute_count')
    combination_count = fields.Integer(compute='_compute_count')

    @api.depends('target_products', 'virtual_products')
    def _compute_count(self):
        for _id in self:
            _id.bom_count = len(_id.target_products.filtered('is_bom'))
            _id.product_count = len(_id.target_products)
            _id.combination_count = len(_id.virtual_products)

    @api.onchange('source_templates')
    def onchange_source_templates(self):
        attribute_ids = self.source_templates.mapped('attribute_ids')
        value_ids = self.source_templates.mapped('attribute_value_ids')
        self.source_values = self.source_values.filtered(lambda r: r in value_ids)
        if self.source_category not in attribute_ids.mapped('category_id'):
            self.source_category = None
        if self.source_attribute not in attribute_ids:
            self.source_attribute = None
        domain = {
            'source_category': [('id', 'in', attribute_ids.mapped('category_id').ids)],
            'source_attribute': [('id', 'in', attribute_ids.ids)],
            'source_selection': [('id', 'in', value_ids.ids)],
            'source_values': [('id', 'in', value_ids.ids)],
        }
        return {'domain': domain}

    @api.onchange('type')
    def onchange_type(self):
        template_domain = []
        if self.type == 'any':
            template_domain = []
        elif self.type in ['normal', 'party', 'labor']:
            self.source_templates = self.source_templates.filtered(lambda r: r.categ_type == self.type)
            self.target_products = self.target_products.filtered(lambda r: r.categ_type == self.type)
            template_domain = [('categ_type', '=', self.type)]
        else:
            self.source_templates = self.source_templates.filtered(lambda r: r.bom_type == self.type)
            self.target_products = self.target_products.filtered(lambda r: r.bom_type == self.type)
            template_domain = [('bom_type', '=', self.type)]
        return {'domain': {'source_templates': template_domain}}

    @api.onchange('source_selection')
    def onchange_source_selection(self):
        new_values = []
        for value_id in self.source_selection - self.source_values:
            new_values.append((4, value_id.id, False))
        self.source_values = new_values

    def create_combination_btn(self):
        self.ensure_one()
        AttributeValue = self.env['product.template.attribute.value']

        product_cmds = []
        for template in self.source_templates:
            template_type = template.bom_type if template.categ_type == 'bom' else template.categ_type

            # Combine attribute values
            value_lst = []
            for line in template.valid_product_template_attribute_line_ids:
                line_values = line.product_template_value_ids
                line_values = line_values.filtered(lambda r: r.product_attribute_value_id in self.source_values)
                if line_values:
                    value_lst.append(line_values)

            # Get existing combinations
            existing_products = {
                r.product_template_attribute_value_ids: r
                for r in template.product_variant_ids.sorted('active')
            }
            existing_values = [r.attribute_value_ids for r in self.virtual_products]
            existing_values += existing_products.keys()

            # Create new products
            for combination in itertools.product(*value_lst):
                combination = AttributeValue.concat(*combination)
                if combination not in existing_values:
                    product_cmds.append((0, False, {
                        'template_id': template.id,
                        'attribute_value_ids': [(6, 0, combination.ids)]
                    }))

        self.virtual_products = product_cmds
        return self.reload()

    def remove_combination_btn(self):
        self.ensure_one()
        self.virtual_products = None
        return self.reload()

    def create_product_btn(self):
        self.ensure_one()
        Product = self.env['product.product']
        product_cmds = []
        for line in self.virtual_products:
            product_id = Product.create({
                'product_tmpl_id': line.template_id.id,
                'product_template_attribute_value_ids': [(6, False, line.attribute_value_ids.ids)],
                'party_id': line.template_id.party_id.id,
                'workcenter_id': line.template_id.workcenter_id.id,
                'min_members': line.template_id.min_members,
                'max_members': line.template_id.max_members
            })
            product_cmds.append((4, product_id.id, False))
        self.target_products = product_cmds
        self.virtual_products = False
        return self.reload()

    def create_bom_btn(self):
        self.ensure_one()

    def reload(self):
        line_cmds = []
        for line in self.virtual_products:
            line_cmds.append((0, False, {
                'template_id': line.template_id.id,
                'attribute_value_ids': [(6, 0, line.attribute_value_ids.ids)]
            }))

        action = self.env.ref('aci_product.create_product_wizard_action').read()[0]
        action['context'] = {
            'default_type': self.type,
            'default_source_templates': [(6, False, self.source_templates.ids)],
            'default_source_values': [(6, False, self.source_values.ids)],
            'default_virtual_products': line_cmds,
            'default_target_products': [(6, False, self.target_products.ids)]
        }
        return action


class CreateProductWizardLine(models.TransientModel):
    _name = 'create.product.wizard.line'
    _description = 'Create Product Wizard Combination'

    wizard_id = fields.Many2one('create.product.wizard')
    template_id = fields.Many2one('product.template')
    attribute_value_ids = fields.Many2many('product.template.attribute.value')
