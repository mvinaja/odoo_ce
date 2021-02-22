# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError
from collections import Counter

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    _order = 'categ_sequence, sequence'

    attribute_config = fields.Boolean('Original Attrib. Conf.', default=False)
    freecad_ignore = fields.Boolean(default=False)
    step_type = fields.Selection([
        ('unit', 'Unit'),
        ('integer', 'Integer'),
        ('float', 'Fraction'),
        ('check', 'Check'),
        ('progress_qty', 'Progress x QTY'),
        ('progress_unit', 'Progress x Unit')
    ], default='float')
    quality_restriction = fields.Boolean()

    categ_sequence = fields.Integer(
        related='categ_id.sequence', string='Categ. Seq.', readonly=True, store=True)
    categ_path = fields.Char(related='categ_id.parent_path', readonly=True, store=True)
    categ_type = fields.Selection(related='categ_id.type', readonly=True, store=True)

    party_id = fields.Many2one('product.product', 'Party')

    is_bom = fields.Boolean(related='categ_id.is_bom', readonly=True, store=True)
    bom_type = fields.Selection(related='categ_id.bom_type', readonly=True, store=True)
    position_key = fields.Many2one(related='categ_id.position_key', readonly=True, store=True)
    position_type = fields.Selection(related='position_key.type', readonly=True, store=True)

    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center')
    min_members = fields.Integer('Min Crew Members', default=1)
    max_members = fields.Integer('Max Crew Members', default=1)

    attribute_ids = fields.Many2many('product.attribute', string='Attributes')
    attribute_value_ids = fields.Many2many(
        'product.attribute.value', compute='_compute_attribute_ids', store=True)

    mold_id = fields.Many2one('product.template')
    mold_group_ids = fields.One2many('product.template', 'mold_id', string='Mold Group')

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Template name already exists.')]

    def _create_variant_ids(self):
        template_ids = self.filtered('attribute_config')
        return super(ProductTemplate, template_ids)._create_variant_ids()

    @api.depends('attribute_line_ids.value_ids')
    def _compute_attribute_ids(self):
        for _id in self:
            _id.attribute_value_ids = _id.attribute_line_ids.mapped('value_ids')

    def get_product(self, attribute_value_ids):
        self.ensure_one()
        TemplateValue = self.env['product.template.attribute.value']
        template_values = {}
        for line_value in self.attribute_line_ids.product_template_value_ids:
            template_values[line_value.product_attribute_value_id] = line_value

        combination = TemplateValue
        for value_id in attribute_value_ids:
            combination += template_values.get(value_id, TemplateValue)
        return self._get_variant_for_combination(combination)

    @api.model
    def get_mrp_models(self):
        '''Manufacturing business models to check for updates'''
        return {
            'mrp.bom': 'a Bill of Material',
            'mrp.bom.line': 'a BOM Line'
        }

    @api.constrains('categ_id')
    def _check_categ_id(self):
        '''Restrict valid categories of type bill of material and simple'''
        if self.filtered(lambda r: r.categ_id.type == 'view'):
            raise UserError(
                _('Product categories of type "View" cannot contains products.'))

    @api.constrains('min_members', 'max_members')
    def _check_crew_members(self):
        '''Check for min and max crew members restrictions'''
        for _id in self:
            if _id.min_members > _id.max_members:
                raise UserError(
                    _('Max crew members must be greater than min crew members.'))

    def _check_properties(self, bom_type):
        # Get restricted manufacturing business models
        model_lst = self.get_mrp_models()
        bom_type = bom_type or False

        # Filter non updated product templates
        for _id in self.filtered(lambda r: r.bom_type != bom_type):
            # Evaluate if a product variant is being used by a restricted model
            for model, name in model_lst.items():
                Model = self.env[model]
                if Model.search_count([('product_id', 'in', _id.product_variant_ids.ids)]):
                    # Merde
                    raise UserError(
                        _('Cannot update manufacturing properties for template "{}".\
                        A product variant is currently being used by {}.'.format(_id.name, name)))

    def product_configurator_btn(self):
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = {
            'default_type': self.bom_type if self.categ_type == 'bom' else self.categ_type,
            'default_target_templates': [(4, self.id, False)],
            'default_target_products': [(6, False, self.product_variant_ids.ids)],
            'default_source_values': self.attribute_value_ids.ids,
            'has_defaults': True,
            'target_templates': [(4, self.id, False)],
            'target_products': [(6, False, self.product_variant_ids.ids)],
            'attribute_value_ids': self.attribute_value_ids.ids
        }
        return action

    def create_product_btn(self):
        action = self.env.ref('aci_product.create_product_wizard_action').read()[0]
        action['context'] = {
            'default_type': self.bom_type if self.categ_type == 'bom' else self.categ_type,
            'default_source_templates': [(4, self.id, False)],
            'default_source_values': [(6, False, self.attribute_value_ids.ids)]
        }
        return action

    def show_form_btn(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'view_mode': 'form',
            'res_model': 'product.template',
            'res_id': self.id,
            'target': 'current'
        }
        return action

    def show_bom_btn(self):
        # Get active budget
        action = self.env.ref('mrp.mrp_bom_form_action').read()[0]
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {}
        return action


class ProductProduct(models.Model):
    _inherit = 'product.product'

    sequence = fields.Integer(default=0)
    sequence_template = fields.Integer(
        'Template Seq.', related='product_tmpl_id.sequence', readonly=True, store=True)
    sequence_category = fields.Integer(
        'Category Seq.', related='product_tmpl_id.categ_sequence', readonly=True, store=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True)

    is_bom = fields.Boolean(related='categ_id.is_bom', readonly=True, store=True)
    neodata_id = fields.Integer('Neodata ID')
    indivisible = fields.Boolean(default=True)
    freecad_ignore = fields.Boolean(default=False)
    step_type = fields.Selection([
        ('unit', 'Unit'),
        ('integer', 'Integer'),
        ('float', 'Fraction'),
        ('check', 'Check'),
        ('progress_qty', 'Progress x QTY'),
        ('progress_unit', 'Progress x Unit')
    ], default='float')
    add_value = fields.Boolean('Extra Value')

    has_bom = fields.Boolean(compute='_compute_has_bom', store=True)
    bom_ids = fields.One2many('mrp.bom', 'product_id')

    fasar_crew = fields.Float()
    fasar_base = fields.Float(bom_dependent=True)
    fasar_factor = fields.Float(bom_dependent=True)

    pricelist_id = fields.Many2one(
        'product.pricelist', 'Price List', bom_dependent=True, ondelete='restrict')
    manual_price = fields.Boolean('Fixed Price', bom_dependent=True)
    context_price = fields.Float(bom_dependent=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('progress', 'Validated'),
        ('readonly', 'Approved')
    ], default='draft', bom_dependent=True)

    party_id = fields.Many2one('product.product', 'Party')
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center')
    min_members = fields.Integer('Min Crew Members', default=1)
    max_members = fields.Integer('Max Crew Members', default=1)

    attribute_value_ids = fields.Many2many(
        'product.attribute.value', compute='_compute_attribute_value_ids', store=True)

    def write(self, values):
        template_values = self.mapped('product_template_attribute_value_ids')
        old_values = template_values.mapped('product_attribute_value_id')
        old_values = old_values.filtered(lambda r: r.state == 'readonly')
        super(ProductProduct, self).write(values)

        # Check for a readonly attribute value replace
        template_values = self.mapped('product_template_attribute_value_ids')
        new_values = template_values.mapped('product_attribute_value_id')
        new_values = new_values.filtered(lambda r: r.state == 'readonly')
        is_mrp_chief = self.env.user.has_group('aci_product.group_mrp_chief')
        if not is_mrp_chief and (old_values - new_values):
            raise UserError(
                _('Only a MRP Chief can replace an approved attribute value.'))

        fasar_fields = ['fasar_base', 'fasar_factor']
        price_fields = ['context_price', 'pricelist_id', 'manual_price']
        price_fields.extend(fasar_fields)
        states = self.mapped('state')
        if 'state' in values.keys() and not is_mrp_chief:
            raise UserError(_('Only a MRP Chief can approve a context price.'))
        elif any(r == 'readonly' for r in states) and any(r in price_fields for r in values.keys()):
            raise UserError(_('Cannot update an approved context price.'))

        # Recompute FASAR
        if any(k in fasar_fields for k in values.keys()):
            for _id in self.filtered(lambda r: r.categ_type == 'labor'):
                _id.context_price = _id.fasar_base * _id.fasar_factor

    @api.depends('complete_name')
    def name_get(self):
        result = []
        for _id in self:
            result.append((_id.id, _id.complete_name))
        return result

    @api.constrains('product_template_attribute_value_ids')
    def _check_attribute_values(self):
        for _id in self:
            attributes = [r.attribute_id.id for r in _id.product_template_attribute_value_ids]
            if any(r > 1 for r in Counter(attributes).values()):
                raise UserError(
                    _('Products variants can only have one value per attribute.'))

    @api.constrains('fasar_base', 'fasar_factor')
    def _check_fasar(self):
        material_ids = self.filtered(lambda r: r.position_key.type == 'labor')
        if len(material_ids):
            raise UserError(
                _('Only products of type crew and labor may have FASAR.'))

    @api.constrains('context_price')
    def _check_context_price(self):
        for _id in self.filtered(lambda r: r.context_price):
            if not self.env.user.get_context_bom():
                raise UserError(
                    _('Please select a budget context on the systray menu to perform this operation.'))

    @api.depends('product_tmpl_id.name',
        'product_template_attribute_value_ids.product_attribute_value_id.name',
        'product_template_attribute_value_ids.product_attribute_value_id.code')
    def _compute_complete_name(self):
        for _id in self:
            values = _id.product_template_attribute_value_ids
            values = values.sorted(key=lambda r: r.attribute_line_id.sequence)
            values = [r.code or r.name for r in values.product_attribute_value_id]
            name = values and '{} ({})'.format(_id.name, ','.join(values)) or _id.name
            if self.env.context.get('display_default_code', True) and _id.default_code:
                _id.complete_name = '[{}] {}'.format(_id.default_code, name)
            else:
                _id.complete_name = name

    @api.depends('product_template_attribute_value_ids.product_attribute_value_id')
    def _compute_attribute_value_ids(self):
        for _id in self:
            template_values = _id.product_template_attribute_value_ids
            _id.attribute_value_ids = template_values.mapped('product_attribute_value_id')

    @api.depends('bom_ids')
    def _compute_has_bom(self):
        for _id in self:
            _id.has_bom = len(_id.bom_ids) > 0

    def product_configurator_btn(self):
        action = self.env.ref('aci_product.product_configurator_wizard_action').read()[0]
        action['context'] = {
            'default_type': self.bom_type if self.categ_type == 'bom' else self.categ_type,
            'default_apply_to': 'product',
            'default_target_templates': self.product_tmpl_id.ids,
            'default_target_products': self.ids,
            'default_source_values': self.attribute_value_ids.ids,
            'has_defaults': True,
            'target_templates': self.product_tmpl_id.ids,
            'target_products': self.ids,
            'attribute_value_ids': self.attribute_value_ids.ids
        }
        return action

    def show_form_btn(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': self.complete_name,
            'view_mode': 'form',
            'res_model': 'product.product',
            'res_id': self.id,
            'target': 'current'
        }
        return action
