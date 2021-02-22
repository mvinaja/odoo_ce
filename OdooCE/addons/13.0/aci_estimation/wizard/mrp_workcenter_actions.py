# -*- coding: utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import UserError

class MrpWorkcenterActions(models.TransientModel):
    _name = 'mrp.workcenter.actions'
    _description = 'mrp.workcenter.actions'

    field_name = fields.Selection([('resource_calendar_id', 'Calendar'),
                                   ('period_group_id', 'Period Group')])
    resource_calendar_id = fields.Many2one('resource.calendar', 'Working Schedule')
    period_group_id = fields.Many2one('payment.period.group', 'Payment Period Groups')
    workcenter_ids = fields.Many2many('mrp.workcenter')

    @api.model
    def default_get(self, fields):
        res = super(MrpWorkcenterActions, self).default_get(fields)
        res['workcenter_ids'] = self._context.get('active_ids', [])
        return res

    def change_field(self):
        if self.field_name == 'resource_calendar_id':
            value = self.resource_calendar_id.id
        elif self.field_name == 'period_group_id':
            value = self.period_group_id.id
        self.workcenter_ids.write({self.field_name: value})


class MrpWorkcenterProductivityWizard(models.TransientModel):
    _name = 'mrp.workcenter.productivity.wizard'
    _description = 'mrp.workcenter.productivity.wizard'

    def _get_default_estimation_ids(self):
        Estimation = self.env['mrp.estimation']
        context = self.env.context
        input_ids = self.env['mrp.workcenter.productivity'].browse(context.get('active_ids'))
        workcenter_ids = input_ids.mapped('resource_id')
        date_ids = input_ids.mapped('final_start_date')
        date_ids.sort(reverse=True)
        if input_ids:
            if len(input_ids.mapped('warehouse_id')) > 1:
                _id = None
            else:
                estimation_ids = Estimation.search([('workcenter_id', 'in', workcenter_ids.ids),
                                                    ('end_period', '>=', date_ids[0]),
                                                    ('estimation_type', '=', 'period'),
                                                    ('warehouse_id', '=', input_ids[0].warehouse_id.id),
                                                    ('period_status', 'in', ('waiting_approval', 'open'))],
                                                   order='start_period ASC').ids
                if estimation_ids:
                    _id = estimation_ids[0]
                else:
                    _id = None
        else:
            _id = None
        return _id

    def _get_estimation_ids(self):
        Estimation = self.env['mrp.estimation']
        context = self.env.context
        input_ids = self.env['mrp.workcenter.productivity'].browse(context.get('active_ids'))
        workcenter_ids = input_ids.mapped('resource_id')
        date_ids = input_ids.mapped('final_start_date')
        date_ids.sort(reverse=True)
        if input_ids:
            estimation_ids = Estimation.search([('workcenter_id', 'in', workcenter_ids.ids),
                                                ('end_period', '>=', date_ids[0]),
                                                ('estimation_type', '=', 'period'),
                                                ('warehouse_id', 'in', input_ids.mapped('warehouse_id').ids),
                                                ('period_status', 'in', ('waiting_approval', 'open'))]).ids
        else:
            estimation_ids = []
        return [('id', 'in', estimation_ids)]

    type = fields.Selection([('percentage', 'Percentage'),
                             ('selection', 'Selection'),
                             ('discount', 'Discount'),
                             ('deposit', 'Deposit'),
                             ('extra', 'Extra')], default='selection')
    productivity_ids = fields.Many2many('mrp.workcenter.productivity', 'mrp_workcenter_productivity_wizard_rel',
                                        'wizard_id', 'productivity_id')
    input_ids = fields.One2many('mrp.workcenter.productivity.input.wizard', 'base_id')
    estimation_id = fields.Many2one('mrp.estimation', domain=_get_estimation_ids, default=_get_default_estimation_ids)
    qty_status = fields.Selection([('pending', 'Pending'),
                                   ('waiting_approval', 'Waiting Approval'),
                                   ('approved', 'Approved')], default='pending', required=True)
    input_type = fields.Selection([('percentage', 'Percentage'),
                                   ('qty', 'Quantity')], default='percentage', required=True)
    discount = fields.Float(default=100.00)
    deposit = fields.Float(string='Warranty')

    workorder_extra = fields.Float('WorkOrder Extra')
    workorder_extra_available = fields.Float('Available')
    approved_extra = fields.Float('Approved')

    @api.model
    def default_get(self, fields):
        res = super(MrpWorkcenterProductivityWizard, self).default_get(fields)
        context = self.env.context
        input_ids = self.env['mrp.workcenter.productivity'].browse(context.get('active_ids')).filtered(lambda r: r.available is True and
                                                                                                       r.qty_status != 'approved')
        if len(input_ids.mapped('workorder_by_step')) != 1:
            raise UserError('Select one workorder')

        if input_ids[0].discount_validated is True and 'type' in res and res['type'] == 'extra':
            raise UserError('Discount already implemented')

        if input_ids[0].warranty_validated is True and 'type' in res and res['type'] == 'discount':
            raise UserError('Warranty already implemented')

        if input_ids[0].workorder_extra <= 0 and 'type' in res and res['type'] == 'extra':
            raise UserError('{} does not have any extra'.format(input_ids[0].workorder_by_step.product_wo.complete_name))

        res['workorder_extra'] = input_ids[0].workorder_extra
        res['workorder_extra_available'] = input_ids[0].workorder_extra_available
        res['productivity_ids'] = [(6, False, input_ids.ids)]
        in_ids = []
        for input_id in input_ids:
            in_ids.append((0, False, {'productivity_id': input_id.id,
                                      'product_id': input_id.product_id.id,
                                      'workorder_id': input_id.workorder_by_step.id,
                                      'analytic_name': input_id.analytic_name,
                                      'workorder_extra': input_id.workorder_extra,
                                      'workorder_extra_available': input_id.workorder_extra_available}))
        res['input_ids'] = in_ids
        return res

    def approve_btn(self):
        if self.approved_extra < 0 or self.discount < 0 or self.deposit < 0:
            raise UserError('Qty needs to be bigger or equal to 0')

        if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
            raise UserError('You are not allowed to do this process')
        if self.type == 'selection':
            if self.estimation_id and self.estimation_id.period_status not in ('open', 'waiting_approval'):
                raise UserError('This Estimation has already been send to pay')

            cmd = {'qty_status': self.qty_status}
            if self.qty_status != 'pending':
                cmd.update({'estimation_id': self.estimation_id.id})
            for productivity_id in self.productivity_ids.filtered(lambda r: r.qty_status != 'approved'):
                productivity_id.write(cmd)

        elif self.type == 'extra':
            if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
                raise UserError('You are not allowed to do this process')

            approved_extra = self.approved_extra / len(self.input_ids)
            if self.approved_extra > self.workorder_extra_available:
                raise UserError('{} has an operation extra limit of {}'.format(self.input_ids[0].workorder_id.product_wo.complete_name,
                                                                               self.input_ids[0].workorder_id.operation_extra_available))

            for input_id in self.input_ids:
                input_id.productivity_id.operation_extra = approved_extra

        elif self.type == 'discount':
            if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
                raise UserError('You are not allowed to do this process')
            for productivity_id in self.productivity_ids.filtered(lambda r: r.qty_status != 'approved'):
                if self.input_type == 'qty':
                    qty = self.discount
                else:
                    qty = self.discount * productivity_id.partial_amount / 100

                if qty > productivity_id.partial_amount:
                    raise UserError('Discount exceeded ( trying to discount {} from {})'.format(qty, productivity_id.partial_amount))

                discount_validated = True if qty > 0 else False
                productivity_id.write({'discount': qty, 'discount_validated': discount_validated})

        elif self.type == 'deposit':
            if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
                raise UserError('You are not allowed to do this process')
            for productivity_id in self.productivity_ids.filtered(lambda r: r.qty_status != 'approved'):
                if self.input_type == 'qty':
                    qty = self.deposit
                else:
                    qty = self.deposit * productivity_id.discount_amount / 100

                if qty > productivity_id.discount_amount:
                    raise UserError('Warranty exceeded ( trying to set a warranty of {} from {})'.format(qty, productivity_id.discount_amount))
                warranty_validated = True if qty > 0 else False
                discount_validated = True if productivity_id.discount > 0 else False
                productivity_id.write({'deposit': qty, 'discount_validated': discount_validated, 'warranty_validated': warranty_validated})


class MrpWorkcenterProductivityInputWizard(models.TransientModel):
    _name = 'mrp.workcenter.productivity.input.wizard'
    _description = 'mrp.workcenter.productivity.input.wizard'

    base_id = fields.Many2one('mrp.workcenter.productivity.wizard')
    productivity_id = fields.Many2one('mrp.workcenter.productivity')
    product_id = fields.Many2one('product.product')
    workorder_id = fields.Many2one('mrp.workorder')
    analytic_name = fields.Char()
    workorder_extra = fields.Float()
    workorder_extra_available = fields.Float()
    approved_extra = fields.Integer('Appvd.')
