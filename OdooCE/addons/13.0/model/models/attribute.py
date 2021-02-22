# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class ProductAttributeCategory(models.Model):
    _inherit = 'product.attribute.category'

    _sql_constraints = [
        ('unique_attrib_categ_name', 'unique(name)', 'Attribute category name already exists.')]

    attribute_count = fields.Integer('Attributes', compute='_compute_product_count')
    value_count = fields.Integer('Values', compute='_compute_product_count')
    template_count = fields.Integer('Product Templates', compute='_compute_product_count')
    product_count = fields.Integer('Product Variants', compute='_compute_product_count')
    bom_count = fields.Integer('Bill Of Materials', compute='_compute_product_count')

    value_ids = fields.One2many('product.attribute.value', 'category_id', 'Related Values')

    def _compute_product_count(self):
        Bom = self.env['mrp.bom']
        for _id in self:
            _id.attribute_count = len(_id.attribute_ids)
            _id.value_count = len(_id.attribute_ids.value_ids)
            _id.template_count = sum(_id.attribute_ids.mapped('template_count'))
            _id.product_count = sum(_id.attribute_ids.mapped('product_count'))

            templates = _id.attribute_ids.attribute_line_ids.product_tmpl_id
            _id.bom_count = Bom.search_count([('product_tmpl_id', 'in', templates.ids)])

    def show_attribute_btn(self):
        self.ensure_one()
        action = self.env.ref('product.attribute_action').read()[0]
        action['domain'] = [('id', 'in', self.attribute_ids.ids)]
        return action

    def show_value_btn(self):
        self.ensure_one()
        action = self.env.ref('aci_product.product_attribute_value_action').read()[0]
        action['domain'] = [('id', 'in', self.attribute_ids.value_ids.ids)]
        return action

    def show_template_btn(self):
        self.ensure_one()
        templates = self.attribute_ids.attribute_line_ids.product_tmpl_id
        action = self.env.ref('mrp.product_template_action').read()[0]
        action['domain'] = [('id', 'in', templates.ids)]
        return action

    def show_product_btn(self):
        self.ensure_one()
        products = self.attribute_ids.value_ids.product_ids
        action = self.env.ref('product.product_normal_action').read()[0]
        action['domain'] = [('id', 'in', products.ids)]
        return action

    def show_bom_btn(self):
        self.ensure_one()
        Bom = self.env['mrp.bom']
        templates = self.attribute_ids.attribute_line_ids.product_tmpl_id
        bom_ids = Bom.search([('product_tmpl_id', 'in', templates.ids)])
        action = self.env.ref('mrp.mrp_bom_form_action').read()[0]
        action['domain'] = [('id', 'in', bom_ids.ids)]
        return action


class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    @api.model
    def _get_sequence(self):
        attribute_ids = self.search([])
        max_sequence = max(attribute_ids.mapped('sequence') or [0]) + 1
        while max_sequence % 5:
            max_sequence += 1
        return max_sequence
    sequence = fields.Integer(default=_get_sequence)

    category_id = fields.Many2one(required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('readonly', 'Approved')
    ], default='draft')

    create_variant = fields.Selection(default='dynamic')

    template_count = fields.Integer('Product Templates', compute='_compute_product_count', store=True)
    product_count = fields.Integer('Product Variants', compute='_compute_product_count', store=True)
    value_count = fields.Integer('Attribute Values', compute='_compute_product_count', store=True)

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Attribute name already exists.')]

    def write(self, values):
        # Check if attribute has been approved
        self.check_readonly(self, values)

        # Update product's attribute lines category
        if 'category_id' in values.keys():
            attribute_lines = self.attribute_line_ids
            attribute_lines.write({'category_id': values.get('category_id')})

        return super(ProductAttribute, self).write(values)

    def copy(self, values=None):
        values = values or {}
        values.update({'name': '{} (copy)'.format(self.name)})
        return super(ProductAttribute, self).copy(values)

    @api.model
    def check_readonly(self, record_ids, values):
        # Check for attribute update rights
        is_mrp_chief = self.env.user.has_group('aci_product.group_mrp_chief')
        is_readonly = any(r == 'readonly' for r in record_ids.mapped('state'))
        if not is_mrp_chief and is_readonly:
            raise exceptions.ValidationError(
                _('Only a MRP Chief can update an approved attribute or value.'))
        elif not is_mrp_chief and 'state' in values.keys():
            raise exceptions.ValidationError(
                _('Only a MRP Chief can approve attributes or values.'))

    @api.depends('product_tmpl_ids', 'value_ids', 'value_ids.product_ids')
    def _compute_product_count(self):
        for _id in self:
            _id.template_count = len(_id.product_tmpl_ids)
            _id.product_count = len(_id.value_ids.product_ids)
            _id.value_count = len(_id.value_ids)

    def show_form_btn(self):
        self.ensure_one()
        form_view = self.env.ref('aci_product.product_attribute_form')
        action = self.env.ref('product.attribute_action').read()[0]
        action['views'] = [(form_view.id, 'form')]
        action['res_id'] = self.id
        return action

    def show_template_btn(self):
        self.ensure_one()
        action = self.env.ref('mrp.product_template_action').read()[0]
        action['domain'] = [('id', 'in', self.product_tmpl_ids.ids)]
        return action

    def show_product_btn(self):
        self.ensure_one()
        action = self.env.ref('product.product_normal_action').read()[0]
        action['domain'] = [('id', 'in', self.value_ids.product_ids.ids)]
        return action

    def show_value_btn(self):
        self.ensure_one()
        action = self.env.ref('aci_product.product_attribute_value_action').read()[0]
        action['domain'] = [('attribute_id', '=', self.id)]
        action['context'] = {'default_attribute_id': self.id}
        return action

    def product_configurator_btn(self):
        self.ensure_one()
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = {
            'default_source_category': self.category_id.id,
            'default_source_attribute': self.id,
            'default_source_values': self.value_ids.ids,
            'has_defaults': True,
            'category_id': self.category_id.id,
            'attribute_id': self.id,
            'attribute_value_ids': self.value_ids.ids
        }
        return action

    def create_value_btn(self):
        self.ensure_one()
        action = self.env.ref('aci_product.create_product_attribute_value_wizard').read()[0]
        action['context'] = {'default_attribute_id': self.id}
        return action

    def create_product_btn(self):
        self.ensure_one()
        templates = self.attribute_line_ids.product_tmpl_id
        action = self.env.ref('aci_product.create_product_wizard_action').read()[0]
        product = templates and templates[0]
        action['context'] = {
            'default_type': product.bom_type if product.is_bom else product.categ_type,
            'default_source_templates': [(6, False, templates.ids)],
            'default_source_values': [(6, False, self.value_ids.ids)]
        }
        return action


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    @api.model
    def _get_sequence(self):
        attribute = self.env.context.get('default_attribute_id')
        value_ids = self.search([('attribute_id', '=', attribute)])
        max_sequence = max(value_ids.mapped('sequence') or [0]) + 1
        while max_sequence % 5:
            max_sequence += 1
        return max_sequence

    sequence = fields.Integer(default=_get_sequence)

    code = fields.Char()
    code_length = fields.Integer('Code Length', default=4)
    manual_code = fields.Boolean('Manual Code')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('readonly', 'Approved')
    ], default='draft')

    category_id = fields.Many2one(related='attribute_id.category_id', readonly=True, store=True)
    category_sequence = fields.Integer(
        'Category Seq.', related='category_id.sequence', readonly=True, store=True)

    template_count = fields.Integer('Product Templates', compute='_compute_product_count', store=True)
    product_count = fields.Integer('Product Variants', compute='_compute_product_count', store=True)

    product_ids = fields.Many2many('product.product', string='Variants', readonly=True)

    @api.model
    def create(self, values):
        value_ids = super(ProductAttributeValue, self).create(values)
        value_ids.compute_code()
        return value_ids

    def write(self, values):
        Attribute = self.env['product.attribute']

        # Check for write rights
        Attribute.check_readonly(self.attribute_id, values)
        Attribute.check_readonly(self, values)

        # Do it!
        super(ProductAttributeValue, self).write(values)

        # Recompute attribute value code
        if any(f in ['name', 'manual_code', 'code_length'] for f in values.keys()):
            self.compute_code()

    @api.depends('name', 'code')
    def name_get(self):
        result = []
        for _id in self:
            name = _id.code if _id.code else _id.name
            result.append((_id.id, name))
        return result

    def compute_code(self):
        """Compute attribute value code"""
        for _id in self.filtered(lambda r: not r.manual_code):
            domain = [
                ('id', '!=', _id.id),
                ('attribute_id', '=', _id.attribute_id.id)]

            code = _id.name[0:_id.code_length]
            code_index = _id.code_length
            code_suffix = 0

            while self.search_count(domain + [('code', '=', code)]):
                code_index += 1
                if code_index < len(_id.name):
                    code = _id.name[0:code_index]
                else:
                    code_suffix += 1
                    code = '{}_{}'.format(_id.name, code_suffix)
            _id.code = code

    @api.depends('product_ids',
        'pav_attribute_line_ids.value_ids', 'pav_attribute_line_ids.product_tmpl_id')
    def _compute_product_count(self):
        for _id in self:
            _id.template_count = len(_id.pav_attribute_line_ids.product_tmpl_id)
            _id.product_count = len(_id.product_ids)

    def show_template_btn(self):
        self.ensure_one()
        templates = self.pav_attribute_line_ids.product_tmpl_id
        action = self.env.ref('mrp.product_template_action').read()[0]
        action['domain'] = [('id', 'in', templates.ids)]
        return action

    def show_product_btn(self):
        self.ensure_one()
        action = self.env.ref('product.product_normal_action').read()[0]
        action['domain'] = [('id', 'in', self.product_ids.ids)]
        return action

    def attribute_configurator_btn(self):
        self.ensure_one()
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = {
            'default_source_category': self.category_id.id,
            'default_source_attribute': self.attribute_id.id,
            'default_source_values': [(4, self.id, False)],
            'default_target_templates': self.pav_attribute_line_ids.product_tmpl_id.ids,
            'has_defaults': True,
            'category_id': self.category_id.id,
            'attribute_id': self.attribute_id.id,
            'attribute_value_ids': self.ids,
            'target_templates': self.pav_attribute_line_ids.product_tmpl_id.ids,
        }
        return action

    def value_configurator_btn(self):
        self.ensure_one()
        Product = self.env['product.product']
        product_ids = Product.search([('attribute_value_ids', '=', self.id)])
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = {
            'default_apply_to': 'product',
            'default_source_category': self.category_id.id,
            'default_source_attribute': self.attribute_id.id,
            'default_source_values': [(4, self.id, False)],
            'default_target_products': product_ids.ids,
            'has_defaults': True,
            'category_id': self.category_id.id,
            'attribute_id': self.attribute_id.id,
            'attribute_value_ids': self.ids,
            'target_products': product_ids.ids,
        }
        return action

    def add_missing_value_btn(self):
        self.ensure_one()

        template_ids = self.env['product.template']
        for template in self.pav_attribute_line_ids.product_tmpl_id:
            products = template.product_variant_ids
            if not any(r == self for r in products.attribute_value_ids):
                template_ids += template
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = {
            'default_source_category': self.category_id.id,
            'default_source_attribute': self.attribute_id.id,
            'default_source_values': [(4, self.id, False)],
            'default_target_templates': template_ids.ids,
            'has_defaults': True,
            'category_id': self.category_id.id,
            'attribute_id': self.attribute_id.id,
            'attribute_value_ids': self.ids,
            'target_templates': template_ids.ids,
        }
        return action


class ProductTemplateAttributeLine(models.Model):
    _inherit = 'product.template.attribute.line'
    _order = 'sequence'

    sequence = fields.Integer()
    category_id = fields.Many2one('product.attribute.category', 'Category')

    _sql_constraints = [
        ('unique_attribute', 'unique(product_tmpl_id, attribute_id)', 'Attribute already exists.')]

    @api.model
    def create(self, values):
        template_lines = self.search([('product_tmpl_id', '=', values.get('product_tmpl_id'))])
        max_sequence = max(template_lines.mapped('sequence') or [0]) + 1
        while max_sequence % 5:
            max_sequence += 1
        values['sequence'] = max_sequence
        return super(ProductTemplateAttributeLine, self).create(values)

    def write(self, values):
        if 'value_ids' in values.keys():

            for _id in self:
                # Store former attribute values
                former_values = _id.value_ids

                # Do it!
                super(ProductTemplateAttributeLine, _id).write(values)

                # Check if a product variant contains a removed attribute value
                products = _id.product_tmpl_id.with_context(active_test=False).product_variant_ids
                values = products.product_template_attribute_value_ids.product_attribute_value_id
                if (former_values - _id.value_ids) & values:
                    raise exceptions.ValidationError(
                        _('Cannot remove an attribute used by a product variant.'))

        else:
            super(ProductTemplateAttributeLine, self).write(values)

    def unlink(self):
        attribute_ids = self.mapped('attribute_id')
        for template_id in self.mapped('product_tmpl_id'):
            attribute_value_ids = template_id.product_variant_ids.product_template_attribute_value_ids
            if attribute_ids & attribute_value_ids.attribute_id:
                raise exceptions.ValidationError(
                    _('Cannot delete an attribute used by a product variant.'))
        super(ProductTemplateAttributeLine, self).unlink()
