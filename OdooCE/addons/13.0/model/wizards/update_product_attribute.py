# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from odoo.exceptions import ValidationError as Alert


class ProductConfiguratorWizard(models.TransientModel):
    _name = 'product.configurator.wizard'
    _description = 'Product Configurator Wizard'

    action = fields.Selection([
        ('append_value', 'Append To'),
        ('remove_value', 'Remove To'),
        ('replace_value', 'Replace To')
    ], default='append_value')

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
    ], 'Type Of', default='any')

    apply_to = fields.Selection([
        ('template', 'Templates'),
        ('product', 'Variants'),
    ], default='template')

    source_category = fields.Many2one('product.attribute.category', 'Source')
    source_attribute = fields.Many2one('product.attribute', 'Attrib.')
    source_selection = fields.Many2many(
        'product.attribute.value', 'product_configurator__source_selection')
    source_values = fields.Many2many(
        'product.attribute.value', 'product_configurator__source_values')
    source_values_count = fields.Integer(compute='_compute_source_values_count')
    target_templates_count = fields.Integer(compute='_compute_source_values_count')

    target_category = fields.Many2one('product.attribute.category', 'Target')
    target_attribute = fields.Many2one('product.attribute', 'T.Attrib.')
    target_selection = fields.Many2many(
        'product.attribute.value', 'product_configurator__target_selection')

    target_templates = fields.Many2many(
        'product.template', 'product_configurator__target_templates', string='Templates')
    target_products = fields.Many2many(
        'product.product', 'product_configurator__target_products', string='Variants')

    replace_line_ids = fields.One2many('product.configurator.wizard.line', 'wizard_id')

    @api.depends('source_values', 'target_templates')
    def _compute_source_values_count(self):
        for _id in self:
            _id.source_values_count = len(_id.source_values)
            _id.target_templates_count = len(_id.target_templates)

    @api.onchange('source_attribute')
    def onchange_source_selection(self):
        if self.source_attribute:
            return {'domain': {'source_values': [('attribute_id', '=', self.source_attribute.id)]}}
        else:
            return {'domain': {'source_values': []}}

    @api.onchange('source_selection')
    def onchange_source_selection(self):
        new_values = []
        for value_id in self.source_selection - self.source_values:
            new_values.append((4, value_id.id, False))
        self.source_values = new_values

    @api.onchange('target_selection')
    def onchange_target_selection(self):
        replace_lines = [r for r in self.replace_line_ids.filtered(lambda r: not r.target_value)]
        target_values = [r.id.origin for r in self.target_selection]
        while replace_lines and target_values:
            line = replace_lines.pop(0)
            line.target_value = target_values.pop(0)
        self.target_selection = None

    @api.onchange('source_values')
    def onchange_source_values(self):
        line_cmds = []
        sequence = self.replace_line_ids.mapped('sequence')
        sequence = sequence and max(sequence) + 1 or 0
        used_values = self.replace_line_ids.mapped('source_value').ids
        for value_id in self.source_selection.filtered(lambda r: r.id.origin not in used_values):
            defaults = {
                'sequence': sequence,
                'source_attribute': value_id.attribute_id.id,
                'source_value': value_id.id.origin
            }
            line_cmds.append((0, False, defaults))
            sequence += 1
        self.replace_line_ids = line_cmds

    @api.onchange('action', 'type', 'apply_to', 'source_values')
    def onchange_type(self):
        domain = {}
        # Filter by product type
        if self.type == 'any':
            product_domain = []
        elif self.type in ['normal', 'party', 'labor']:
            # Simple products
            self.target_templates = self.target_templates.filtered(lambda r: r.categ_type == self.type)
            self.target_products = self.target_products.filtered(lambda r: r.categ_type == self.type)
            product_domain = [('categ_type', '=', self.type)]
        else:
            # Bill of materials
            self.target_templates = self.target_templates.filtered(lambda r: r.bom_type == self.type)
            self.target_products = self.target_products.filtered(lambda r: r.bom_type == self.type)
            product_domain = [('bom_type', '=', self.type)]
        domain['target_templates'] = product_domain
        domain['target_products'] = product_domain

        # Filter by action
        if self.action in ['remove_value', 'replace_value']:
            # Update replace lines
            line_cmds = []
            sequence = self.replace_line_ids.mapped('sequence')
            sequence = sequence and max(sequence) + 1 or 0
            used_values = self.replace_line_ids.mapped('source_value').ids
            for value_id in self.source_values.filtered(lambda r: r.id.origin not in used_values):
                defaults = {
                    'sequence': sequence,
                    'source_attribute': value_id.attribute_id.id,
                    'source_value': value_id.id.origin
                }
                line_cmds.append((0, False, defaults))
                sequence += 1
            self.replace_line_ids = line_cmds

            # Get values's attribute lines
            template_lines = self.source_values.pav_attribute_line_ids
            if template_lines:
                # Remove invalid products
                if self.apply_to == 'template':
                    ids_target = template_lines.product_tmpl_id.ids
                    templates = self.target_templates.filtered(lambda r: r.id.origin in ids_target)
                    self.target_templates = templates
                else:
                    ids_target = template_lines.product_template_value_ids.ptav_product_variant_ids.ids
                    products = self.target_products.filtered(lambda r: r.id.origin in ids_target)
                    self.target_products = products
                product_domain.append(('id', 'in', ids_target))
            else:
                # Remove all products
                self.target_templates = None
                self.target_products = None
        return {'domain': domain}

    def reload(self):
        line_cmds = []
        for line in self.replace_line_ids:
            value = {
                'remove_source': line.remove_source,
                'source_attribute': line.source_attribute.id,
                'source_value': line.source_value.id,
                'target_attribute': line.target_attribute.id,
                'target_value': line.target_value.id
            }
            line_cmds.append((0, False, value))

        context = self.env.context.copy()
        context.update({
            'default_action': self.action,
            'default_type': self.type,
            'default_apply_to': self.apply_to,
            'default_target_templates': [(6, False, self.target_templates.ids)],
            'default_target_products': [(6, False, self.target_products.ids)],
            'default_source_category': self.source_category.id,
            'default_source_attribute': self.source_attribute.id,
            'default_target_category': self.target_category.id,
            'default_target_attribute': self.target_attribute.id,
            'default_source_values': [(6, False, self.source_values.ids)],
            'default_replace_line_ids': line_cmds
        })
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = context
        return action

    def reset_value_btn(self):
        '''Clear source values'''
        self.source_values = None
        self.replace_line_ids = None
        return self.reload()

    def set_value_btn(self):
        '''Append target product's values to source values'''
        if self.apply_to == 'template':
            value_ids = self.target_templates.attribute_value_ids
        else:
            value_ids = self.target_products.attribute_value_ids
        new_values = []
        for value_id in value_ids - self.source_values:
            new_values.append((4, value_id.id, False))
        self.source_values = new_values
        return self.reload()

    def search_product_btn(self):
        '''Get source values products'''
        TemplateValue = self.env['product.template.attribute.value']
        template_lines = self.source_values.pav_attribute_line_ids
        if self.apply_to == 'template':
            self.target_templates = template_lines.product_tmpl_id
        else:
            value_ids = self.source_values
            value_ids = TemplateValue.search([('product_attribute_value_id', 'in', value_ids.ids)])
            self.target_products = value_ids.ptav_product_variant_ids
        return self.reload()

    def remove_product_btn(self):
        '''Clear products'''
        self.target_templates = None
        self.target_products = None
        return self.reload()

    def set_default_btn(self):
        '''Reset source values'''
        self.source_category = self.env.context.get('category_id')
        self.source_attribute = self.env.context.get('attribute_id')
        self.source_values = self.env.context.get('attribute_value_ids')
        self.target_templates = self.env.context.get('target_templates')
        self.target_products = self.env.context.get('target_products')
        return self.reload()

    def create_product_btn(self):
        self.ensure_one()
        action = self.env.ref('aci_product.create_product_wizard_action').read()[0]
        action['context'] = {
            'default_type': self.type,
            'default_source_templates': [(6, False, self.target_templates.ids)],
            'default_source_values': [(6, False, self.source_values.ids)]
        }
        return action

    def get_template_values(self, template_ids):
        template_values = {}
        for template_id in template_ids:
            for line_value in template_id.attribute_line_ids.product_template_value_ids:
                key = (template_id, line_value.product_attribute_value_id.id)
                template_values[key] = line_value.id
        return template_values

    def set_template_values(self, template_id, data):
        '''Update template's attribute lines'''
        template_cmds = []
        template_lines = template_id.attribute_line_ids

        sequence_lst = template_lines.mapped('sequence')
        sequence = sequence_lst and max(sequence_lst) or 5
        for attribute_id, value_ids in data.items():
            # Filter new attribute values
            attrib_line = template_lines.filtered(lambda r: r.attribute_id == attribute_id)
            attrib_values = value_ids - attrib_line.value_ids

            # Evaluate if template already have current attribute
            if not attrib_line:
                # Create a new attribute line
                values = {
                    'sequence': sequence,
                    'category_id': attribute_id.category_id.id,
                    'attribute_id': attribute_id.id,
                    'value_ids': [(6, False, attrib_values.ids)]
                }
                template_cmds.append((0, False, values))

            else:
                # Update attribute line
                value_cmds = []
                for attrib_value in attrib_values.ids:
                    value_cmds.append((4, attrib_value, False))
                template_cmds.append((1, attrib_line.id, {'value_ids': value_cmds}))

        template_id.attribute_line_ids = template_cmds

    def append_value_btn(self):
        ''''''
        # Group source values by attribute
        attributes = {}
        for value_id in self.source_values:
            attribute_id = value_id.attribute_id
            attributes.setdefault(attribute_id, self.env['product.attribute.value'])
            attributes[attribute_id] += value_id

        if self.apply_to == 'template':
            # Append attribute values to target templates
            for template_id in self.target_templates:
                self.set_template_values(template_id, attributes)
        else:
            # Append attribute values to target products
            template_ids = self.target_products.product_tmpl_id
            for template_id in template_ids:
                self.set_template_values(template_id, attributes)
            template_values = self.get_template_values(template_ids)
            for product_id in self.target_products:
                value_cmds = []
                for id_value in [id for r in attributes.values() for id in r.ids]:
                    id_value = template_values.get((product_id.product_tmpl_id, id_value))
                    value_cmds.append((4, id_value, False))
                product_id.product_template_attribute_value_ids = value_cmds
        return self.reload()

    def remove_value_btn(self):
        self.ensure_one()
        if self.apply_to == 'template':
            value_cmds = []
            for id_value in self.source_values.ids:
                value_cmds.append((3, id_value, False))

            for template_id in self.target_templates:
                template_line = template_id.attribute_line_ids
                template_line = template_line.filtered(lambda r: r.value_ids & self.source_values)
                if template_line.value_ids - self.source_values:
                    template_line.value_ids = value_cmds
                else:
                    template_line.unlink()
        else:
            template_values = self.get_template_values(self.target_products.product_tmpl_id)
            for product_id in self.target_products:
                value_cmds = []
                for id_value in self.source_values.ids:
                    id_value = template_values.get((product_id.product_tmpl_id, id_value))
                    value_cmds.append((3, id_value, False))
                product_id.product_template_attribute_value_ids = value_cmds
        return self.reload()

    def replace_value_btn(self):
        self.ensure_one()
        AttributeValue = self.env['product.attribute.value']
        Products = self.env['product.product']

        attributes = {}
        removed_values = AttributeValue
        for line in self.replace_line_ids:
            attribute_id = line.target_value.attribute_id
            attributes.setdefault(attribute_id, self.env['product.attribute.value'])
            attributes[attribute_id] += line.target_value
            if line.remove_source:
                removed_values += line.source_value

        if self.apply_to == 'template':
            templates = self.target_templates
            products = self.target_templates.product_variant_ids
        else:
            templates = self.target_products.product_tmpl_id
            products =  self.target_products

        for template_id in templates:
            self.set_template_values(template_id, attributes)
        template_values = self.get_template_values(templates)
        for product_id in products:
            value_cmds = []
            value_ids = product_id.product_template_attribute_value_ids.product_attribute_value_id
            for line in self.replace_line_ids.filtered(lambda r: r.source_value in value_ids):
                source_val = template_values.get((product_id.product_tmpl_id, line.source_value.id))
                target_val = template_values.get((product_id.product_tmpl_id, line.target_value.id))
                product_values = product_id.product_template_attribute_value_ids.ids
                product_values.append(target_val)
                product_values.remove(source_val)
                product_values = ','.join([str(i) for i in sorted(product_values)])
                products = Products.sudo().with_context(active_test=False).search([
                    ('product_tmpl_id', '=', product_id.product_tmpl_id.id),
                    ('combination_indices', '=', product_values)])
                if products:
                    values = product_id.product_template_attribute_value_ids.product_attribute_value_id
                    names = ', '.join(values.mapped('name'))
                    raise exceptions.ValidationError(
                        _('A product variant with attribute(s) "{}" already exists.'.format(names)))
                else:
                    value_cmds = [(3, source_val, False), (4, target_val, False)]
            product_id.product_template_attribute_value_ids = value_cmds

        # Remove attribute values
        value_cmds = [(3, r, False) for r in removed_values.ids]
        for template_id in templates:
            template_line = template_id.attribute_line_ids
            template_line = template_line.filtered(lambda r: r.value_ids & removed_values)
            if template_line.value_ids - removed_values:
                template_line.value_ids = value_cmds
            else:
                template_line.unlink()
        return self.reload()


class ProductConfiguratorWizardLine(models.TransientModel):
    _name = 'product.configurator.wizard.line'
    _description = 'Product Configurator Wizard Replace'

    sequence = fields.Integer()
    wizard_id = fields.Many2one('product.configurator.wizard')
    source_attribute = fields.Many2one('product.attribute', 'S. Attrib.')
    source_value = fields.Many2one('product.attribute.value')
    remove_source = fields.Boolean(default=True)

    target_attribute = fields.Many2one(
        related='wizard_id.target_attribute', string='T. Attrib.', readonly=True)
    target_value = fields.Many2one('product.attribute.value')
