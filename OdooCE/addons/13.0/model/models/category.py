# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class AccountBudgetPostGroup(models.Model):
    _name = 'account.budget.post.group'
    _description = 'Account Budgetary Position Group'

    sequence = fields.Integer()
    name = fields.Char()
    type = fields.Selection([('direct', 'Direct Cost')])


class AccountBudgetPost(models.Model):
    _inherit = 'account.budget.post'
    _order = 'group_id,sequence,name'

    sequence = fields.Integer()
    group_id = fields.Many2one('account.budget.post.group', required=True, ondelete='restrict')
    type = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('margin', 'Margin'),
            ('markup', 'Markup'),
            ('tax', 'Tax')
        ], default='normal', required=True)
    margin_key = fields.Many2one('account.budget.post', 'Margin Type')

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Budgetary position already exists.')]


class ProductCategory(models.Model):
    _inherit = 'product.category'
    _order = 'sequence'

    @api.model
    def _get_sequence(self):
        category_ids = self.search([])
        max_sequence = max(category_ids.mapped('sequence')) + 1 if category_ids else 5
        while max_sequence % 5:
            max_sequence += 1

        return max_sequence

    sequence = fields.Integer(default=_get_sequence)
    cad_link = fields.Boolean('FreeCAD Link', default=False)

    template_count = fields.Integer('# Templates', compute='_compute_product_count')
    product_count = fields.Integer(compute='_compute_product_count')
    bom_count = fields.Integer('# Context BOMs', compute='_compute_product_count')
    total_bom_count = fields.Integer('# BOMs', compute='_compute_product_count')
    child_count = fields.Integer('# Child', compute='_compute_product_count')

    type = fields.Selection(
        selection=[
            ('view', 'View'),
            ('party', 'Party'),
            ('normal', 'Simple'),
            ('labor', 'Crew & Labor'),
            ('bom', 'Bill Of Material')
        ], string='Category Type', default='view', required=True)

    is_bom = fields.Boolean(
        'Is Bill Of Material', compute='_compute_properties', store=True)
    bom_type = fields.Selection([
        ('budget', 'Budget'),
        ('phase', 'Phase'),
        ('model', 'Model'),
        ('workorder', 'Workorder'),
        ('basic', 'Basic')
    ], 'BOM Type')

    position_key = fields.Many2one('account.budget.post', 'Budgetary Position')
    position_type = fields.Selection(
        'Position Type', related='position_key.type', store=True, readonly=True)

    def write(self, vals):
        '''Categories of type 'view' cannot contains products'''
        Product = self.env['product.template']

        if vals.get('type') == 'view' and Product.search_count([('categ_id', 'in', self.ids)]):
            raise exceptions.ValidationError(
                _('Cannot update category type to "View". This category is already being used by a product.'))

        # Do it!
        return super(ProductCategory, self).write(vals)

    @api.depends('type')
    def _compute_properties(self):
        for _id in self:
            if _id.type in ['view', 'party']:
                _id.is_bom = False
                _id.bom_type = None
                _id.route_ids = None
                _id.position_key = None

            elif _id.type in ['normal', 'labor']:
                _id.is_bom = False
                _id.bom_type = None
                _id.route_ids = None

            elif _id.type == 'bom':
                _id.is_bom = True
                _id.route_ids = [(4, self.env.ref('mrp.route_warehouse0_manufacture').id, False)]

    @api.depends('child_id')
    def _compute_product_count(self):
        Template = self.env['product.template']
        Product = self.env['product.product']
        Bom = self.env['mrp.bom']
        for _id in self:
            _id.template_count = Template.search_count([('categ_id', '=', _id.id)])
            _id.product_count = Product.search_count([('categ_id', '=', _id.id)])
            _id.bom_count = Bom.search_count([('categ_id', '=', _id.id),
                                              ('context_warehouse', '=', self.env.user.get_context_warehouse().id)])
            _id.total_bom_count = Bom.search_count([('categ_id', '=', _id.id)])
            _id.child_count = len(_id.child_id)

    @api.constrains('type', 'is_bom', 'bom_type', 'position_key')
    def _check_properties(self):
        '''Restrict mrp properties'''
        for _id in self:
            if _id.type in ['view', 'party'] and (_id.is_bom or _id.bom_type or _id.position_key):
                raise exceptions.ValidationError(
                    _('Product categories of type "View" or "Party" cannot contains MRP properties.'))

            elif _id.type in ['normal', 'labor', 'party'] and (_id.is_bom or _id.bom_type):
                raise exceptions.ValidationError(
                    _('Only product categories of type "Bill Of Material" must contain BoM properties.'))

            elif _id.type == 'bom' and (not _id.is_bom or not _id.bom_type):
                raise exceptions.ValidationError(
                    _('Product categories of type "Bill Of Material" must contains BoM properties.'))


class ProductUom(models.Model):
    _inherit = 'uom.uom'

    symbol = fields.Char('Symbol')

    _sql_constraints = [
        ('unique_uom_name', 'unique(name)', 'Producty UoM already exists.')]
