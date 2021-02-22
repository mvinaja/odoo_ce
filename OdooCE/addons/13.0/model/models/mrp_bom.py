# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError


class MrpBom(models.Model):
    _name = 'mrp.bom'
    _inherit = ['mrp.bom', 'aci.context', 'mrp.routing.workcenter']

    name = fields.Char(required=False)
    categ_id = fields.Many2one('product.category', 'Product Category', required=True)
    categ_name = fields.Char(
        'Parent Category', related='categ_id.complete_name', readonly=True, store=True)
    categ_path = fields.Char(
        'Category Path', related='categ_id.parent_path', readonly=True, store=True)

    position_key = fields.Many2one(
        related='categ_id.position_key', readonly=True, store=True, index=True)
    bom_type = fields.Selection(
        related='product_tmpl_id.bom_type', readonly=True, store=True, index=True)

    product_uom_id = fields.Many2one(related='product_tmpl_id.uom_id', readonly=True, store=True)
    product_tmpl_id = fields.Many2one(string='Product Template')
    product_id = fields.Many2one(required=True, ondelete='restrict', index=True)
    attribute_value_ids = fields.Many2many(
        related='product_id.product_template_attribute_value_ids', readonly=True)
    party_id = fields.Many2one(related='product_tmpl_id.party_id', store=True)

    routing_id = fields.Many2one('mrp.routing', required=False, ondelete='restrict')
    workcenter_id = fields.Many2one('mrp.workcenter', required=False, ondelete='restrict')

    _sql_constraints = [
        ('unique_bom',
            "unique(product_id, version)",
            "BoM versions must be unique"),
        ('check_model_routing',
            "check(bom_type='model' AND routing_id IS NOT NULL OR bom_type <> 'model')",
            "A routing is required for bill of material of type Model."),
    ]

    @api.model
    def create(self, vals):
        '''Generate a new version number for every new bom'''
        if not vals.get('version'):
            vals['version'] = self.get_version(vals.get('product_id'))
        return super(MrpBom, self).create(vals)

    @api.constrains('bom_type', 'workcenter_id')
    def _check_operation_data(self):
        '''Operations must have a workcenter'''
        if self.filtered(lambda r: r.bom_type == 'workorder' and not r.workcenter_id):
            raise UserError(
                _('A bill of material operation must have a workcenter.'))

        if self.filtered(lambda r: r.bom_type == 'workorder' and not r.routing_id):
            raise UserError(
                _('A bill of material operation must have a routing.'))

    @api.model
    def get_version(self, id_product):
        self._cr.execute('''
            SELECT COALESCE((
                SELECT MAX(version) FROM mrp_bom
                WHERE product_id = %s GROUP BY product_id
            ), 0) AS version
        ''', ([id_product,]))
        return self._cr.dictfetchall()[0]['version'] + 1
