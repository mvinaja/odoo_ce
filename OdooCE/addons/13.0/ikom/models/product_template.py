# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplatePackage(models.Model):
    _name = 'product.template.package'
    _description = 'product.template.package'

    product_tmpl_id = fields.Many2one('product.template')
    categ_id = fields.Many2one('product.category', 'Product Category', required=True)
    quantity = fields.Integer(default=1, required=True)
    is_required = fields.Boolean(default=True)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    package_ids = fields.One2many('product.template.package', 'product_tmpl_id')
    is_package = fields.Boolean(compute='_compute_is_package', store=True)

    @api.depends('categ_id')
    def _compute_is_package(self):
        for r in self:
            r.is_package = True if r.categ_id.name == 'Package' else False
