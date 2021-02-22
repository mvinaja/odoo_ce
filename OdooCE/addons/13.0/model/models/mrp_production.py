# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    supervisor_ids = fields.Many2many('hr.employee', 'mrp_production_supervisor_rel', 'production_id', 'employee_id')
