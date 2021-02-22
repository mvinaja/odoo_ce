# -*- coding: utf-8 -*-

from odoo import models, api, fields, _

class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    activity_group_limit = fields.Integer(string="Max. Activities in block", default=1)
    order_ids = fields.One2many('mrp.workorder', 'resource_id', "Orders")
    time_ids = fields.One2many('mrp.workcenter.productivity', 'resource_id', 'Time Logs')
    resource_calendar_id = fields.Many2one('resource.calendar', inverse='_update_alter_resource_calendar')
    period_group_id = fields.Many2one('payment.period.group', inverse='_update_alter_period_group')
    on_estimation = fields.Boolean(compute='_compute_on_estimation', store=True)
    estimation_type = fields.Selection([('daily', 'Daily'), ('period', 'Period')], default='period')
    employee_ids = fields.Many2many('hr.employee')
    set_operators = fields.Boolean()
    workcenter_role = fields.Selection([('piecework', 'Piecework'),
                                        ('administrative', 'Administrative')], default='piecework')

    def name_get(self):
        result = []
        for r in self:
            workcenter_code = '{}{}'.format(r.code, ' ({})'.format(r.employee_id.code)
            if r.employee_id and r.employee_id.code else '')
            result.append((r.id, workcenter_code))
        return result

    def write(self, vals):
        Employee = self.env['hr.employee']
        if vals.get('employee_id') == 0:
            vals.update({'employee_id': None})

        res = super(MrpWorkcenter, self).write(vals)
        employee_id = Employee.browse([vals.get('employee_id')]) if vals.get('employee_id') else self.employee_id
        if vals.get('period_group_id') and employee_id:
            contract_id = self.env['hr.contract'].search([('employee_id', 'in', employee_id.ids),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            contract_id.period_group_id = vals.get('period_group_id')
        if vals.get('resource_calendar_id') and employee_id:
            contract_id = self.env['hr.contract'].search([('employee_id', 'in', employee_id.ids),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            contract_id.resource_calendar_id = vals.get('resource_calendar_id')
            employee_id.resource_calendar_id = vals.get('resource_calendar_id')
        return res

    @api.depends('employee_id', 'employee_id.tracking_password')
    def _compute_on_estimation(self):
        for _id in self:
            _id.on_estimation = True if _id.employee_id and _id.employee_id.tracking_password else False

    def _update_alter_period_group(self):
        for _id in self:
            alternative_ids = _id.mapped('alternative_workcenter_ids')
            for alternative in alternative_ids:
                alternative.write({'period_group_id': _id.period_group_id.id})

    def _update_alter_resource_calendar(self):
        for _id in self:
            alternative_ids = _id.mapped('alternative_workcenter_ids')
            for alternative in alternative_ids:
                alternative.write({'resource_calendar_id': _id.resource_calendar_id.id})

    @api.model
    def get_stage_ids(self):
        stage_normal = self.env.ref('aci_estimation.aci_workcenter_normal')
        stage_done = self.env.ref('aci_estimation.aci_workcenter_done')
        stage_blocked = self.env.ref('aci_estimation.aci_workcenter_blocked')

        return {
            'normal': stage_normal.id,
            'done': stage_done.id,
            'blocked': stage_blocked.id
        }

    def button_change_est_type(self, context=None):
        estimation_type = {'daily': 'period', 'period': 'daily'}
        for r in self.browse(self.env.context.get('active_ids')):
            r.write({'estimation_type': estimation_type[r.estimation_type]})

    def button_change_role(self, context=None):
        roles = {'piecework': 'administrative', 'administrative': 'piecework'}
        for r in self.browse(self.env.context.get('active_ids')):
            r.write({'workcenter_role': roles[r.workcenter_role]})

    def button_change_set_operators(self, context=None):
        for r in self.browse(self.env.context.get('active_ids')):
            r.write({'set_operators': not r.set_operators})

    def open_form(self):
        return {
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'res_model': 'mrp.workcenter',
            'target': 'current',
            'views': [(self.env.ref('mrp.mrp_workcenter_view').id, 'form')],
        }

    def get_template_employee_btn(self):
        for employee_id in self.template_id.employee_ids:
            if not self.employee_ids.filtered(lambda r: r.id == employee_id.id):
                self.write({'employee_ids': [(4, employee_id.id)]})