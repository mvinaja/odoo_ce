# -*- coding: utf-8 -*-

from odoo import models, fields, api


class MrpWorkorder(models.Model):
    _inherit = ['mrp.workorder', 'aci.gantt.task']
    _name = 'mrp.workorder'

    sequence = fields.Integer()
    quality_restriction = fields.Boolean()

    operation_id = fields.Many2one('mrp.bom')
    operation_line = fields.Many2one('mrp.bom.line')
    min_members = fields.Integer('Base Crew Members', default=1)
    max_members = fields.Integer('Max Crew Members', default=1)

    party_id = fields.Many2one(related='product_id.party_id', store=True, readonly=True)
    categ_id = fields.Many2one(
        related='product_tmpl_id.categ_id', store=True, readonly=True)
    product_tmpl_id = fields.Many2one(
        related='product_wo.product_tmpl_id', store=True, readonly=True)
    product_wo = fields.Many2one('product.product')
    category_name = fields.Char(related='product_id.categ_id.name', store=True, readonly=True)
    gantt_start = fields.Datetime(related='production_id.date_planned_start', store=True, readonly=True)
    prev_link_ids = fields.One2many('mrp.workorder.link', 'current_id', copy=False)
    next_link_ids = fields.One2many('mrp.workorder.link', 'previous_id', copy=False)

    @api.depends('date_start', 'duration_expected')
    def _compute_date_stop(self):
        Calendar = self.env['resource.calendar']

        calendar_id = self.env.ref('aci_gantt.default_calendar')
        schedule_map = calendar_id.get_schedule_map()
        for _id in self:
            start_date = _id.date_start if _id.date_start else _id.gantt_start
            start_date = Calendar.get_next_working_date(start_date, schedule_map)
            _id.date_stop = Calendar.get_end_date(schedule_map, start_date, _id.duration_expected / 60.0)

    @api.model
    def get_working_time(self):
        Production = self.env['mrp.production']

        production_id = Production.browse([self.env.context.get('active_id')])

        calendar = self.env.ref('aci_gantt.default_calendar')
        days = ["mo", "tu", "we", "th", "fr", "sa", "su"]
        res = '{'

        for workorder_id in production_id.workorder_ids:
            for record in calendar:
                weekdays = record._get_weekdays()
                if res != '{':
                    res += ', '
                res += '"' + str(workorder_id.id) + '": '
                onj_str = '{'
                # for day in weekdays[0]:
                for day in weekdays:
                    day = int(day)
                    if onj_str != '{':
                        onj_str += ', '
                    onj_str += '"' + days[day] + '": true'
                res += onj_str + '}'
        res += '}'
        return res


class MrpWorkorderLink(models.Model):
    _inherit = 'aci.gantt.task.link'
    _name = 'mrp.workorder.link'
    _description = 'mrp.workorder.link'

    current_id = fields.Many2one(comodel_name='mrp.workorder')
    previous_id = fields.Many2one(comodel_name='mrp.workorder')
