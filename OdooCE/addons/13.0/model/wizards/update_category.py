# -*- coding: utf-8 -*-

from odoo import models, fields, api


class UpdateCategorySequenceWizard(models.Model):
    _name = 'update.category.sequence.wizard'
    _description = ' '

    increment = fields.Integer('Increment By', default=5)
    start_sequence = fields.Integer('Start From', default=5)


    def update_sequence_btn(self):
        self.ensure_one()
        ProductCategory = self.env['product.category']

        # Get selected categories
        selected_categories = ProductCategory.browse(self.env.context.get('active_ids'))

        # Enumerate
        sequence = self.start_sequence
        for category_id in selected_categories.sorted(key=lambda r: r.sequence):
            category_id.sequence = sequence
            sequence += self.increment


class UpdateCategoryPropertiesWizard(models.Model):
    _name = 'update.category.properties.wizard'
    _description = ' '

    category_id = fields.Many2one('product.category', 'Category')
    category_type = fields.Selection([
        ('view', 'View'),
        ('normal', 'Simple'),
        ('bom', 'Bill Of Material')
    ], 'Type')

    is_bom = fields.Boolean('Is Bill Of Material')
    bom_type = fields.Selection([
        ('budget', 'Budget'),
        ('model', 'Model'),
        ('phase', 'Phase'),
        ('workorder', 'Workorder'),
        ('basic', 'Basic')
    ], 'BOM Type')
    position_key = fields.Many2one('account.budget.post', 'Budgetary Position')

    @api.onchange('category_id')
    def onchange_category_id(self):
        self.category_type = self.category_id.type
        self.is_bom = self.category_id.is_bom
        self.bom_type = self.category_id.bom_type
        self.position_key = self.category_id.position_key.id

    @api.onchange('category_type')
    def onchange_category_type(self):
        if self.category_type == 'normal':
            # Clear bom settings
            self.is_bom = False
            self.bom_type = False

        elif self.category_type == 'bom':
            self.is_bom = True

        elif self.category_type == 'view':
            # Clear all category settings
            self.is_bom = False
            self.bom_type = False
            self.position_key = False


    def update_properties_btn(self):
        self.ensure_one()
        ProductCategory = self.env['product.category']

        # Browse selected categories
        category_ids = ProductCategory.browse(self.env.context.get('active_ids'))

        # Get manufacturing route
        route_cmd = [(4, self.env.ref('mrp.route_warehouse0_manufacture').id, False)]

        # Do it!
        category_ids.write({
            'type': self.category_type,
            'is_bom': self.is_bom,
            'bom_type': self.bom_type,
            'position_key': self.position_key.id,
            'route_ids': route_cmd if self.is_bom else [(5, False, False)]
        })
