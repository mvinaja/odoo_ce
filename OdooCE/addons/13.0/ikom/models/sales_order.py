# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SalesOrderPackage(models.Model):
    _name = 'sale.order.package'
    _description = 'sale.order.package'

    name = fields.Char(compute='_compute_name')
    order_id = fields.Many2one('sale.order', ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template', ondelete='restrict')
    line_ids = fields.One2many('sale.order.line', 'package_id')

    def name_get(self):
        return [(record.id, "%s %s" % (record.product_tmpl_id.name, record.id)) for record in self]

    def _compute_name(self):
        for r in self:
            r.name = "%s %s" % (r.product_tmpl_id.name, r.id)


class SalesOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def _is_inventory_mode(self):
        return self.env.context.get('inventory_mode') is True and self.user_has_groups('stock.group_stock_manager')

    def _domain_lot_id(self):
        if not self._is_inventory_mode():
            return
        domain = [
            "'|'",
                "('company_id', '=', company_id)",
                "('company_id', '=', False)"
        ]
        if self.env.context.get('active_model') == 'product.product':
            domain.insert(0, "('product_id', '=', %s)" % self.env.context.get('active_id'))
        elif self.env.context.get('active_model') == 'product.template':
            product_template = self.env['product.template'].browse(self.env.context.get('active_id'))
            if product_template.exists():
                domain.insert(0, "('product_id', 'in', %s)" % product_template.product_variant_ids.ids)
        else:
            domain.insert(0, "('product_id', '=', product_id)")
        return '[' + ', '.join(domain) + ']'

    package_id = fields.Many2one('sale.order.package', ondelete='cascade')
    package_categ_id = fields.Many2one('product.category')
    is_required = fields.Boolean()
    lot_id = fields.Many2one(
        'stock.production.lot', 'Lot/Serial Number', index=True,
        ondelete='restrict', readonly=True, check_company=True,
        domain=lambda self: self._domain_lot_id())

    def delete_line_btn(self):
        self.unlink()

    def change_product_btn(self):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Change Package Product',
            'res_model': 'package.product.wizard',
            'target': 'new',
            'context': {'default_categ_id': self.package_categ_id.id}
        }


class SalesOrder(models.Model):
    _inherit = 'sale.order'

    package_ids = fields.One2many('sale.order.package', 'order_id')

    @api.model
    def default_get(self, fields):
        result = super(SalesOrder, self).default_get(fields)
        Pricelist = self.env['product.pricelist']
        pricelist_id = Pricelist.search([], limit=1)
        result['pricelist_id'] = pricelist_id.id if pricelist_id else None
        return result

    def add_package(self):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Select IKOM Package',
            'res_model': 'package.wizard',
            'target': 'new'
        }