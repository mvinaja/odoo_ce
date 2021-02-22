# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class MrpPeriodicitySequence(models.Model):
    _name = 'mrp.periodicity.sequence'
    _description = 'mrp.periodicity.sequence'

    code = fields.Char(required=True)
    name = fields.Char('Description', required=True)

    _sql_constraints = [('mrp_periodicity_sequence_unique', 'unique(code)', 'Repeated Code')]


class MrpPeriodicity(models.Model):
    _name = 'mrp.periodicity'
    _description = 'mrp.periodicity'

    code = fields.Char(required=True)
    periodicity_type = fields.Selection([('week', 'Week day'),
                                         ('month', 'Month')])
    name = fields.Char('Description', required=True)

    _sql_constraints = [('mrp_periodicity_week_unique', 'unique(code)', 'Repeated Code')]
