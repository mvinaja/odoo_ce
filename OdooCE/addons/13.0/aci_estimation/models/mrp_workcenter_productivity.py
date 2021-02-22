# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
import datetime
import dateutil
import pytz

class MrpWorkcenterProductivityQuality(models.Model):
    _name = 'mrp.workcenter.productivity.quality'
    _description = 'Input Quality Restrictions'

    productivity_id = fields.Many2one('mrp.workcenter.productivity', string='Input', required=True, ondelete='cascade')
    product_tmpl_rest_id = fields.Many2one('product.template', string='Restriction Template', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Restriction Product', required=True, ondelete='restrict')
    status = fields.Selection([('pending', ''),
                               ('pass', 'Pass'),
                               ('fail', 'Fail')], default='pending')

    @api.onchange('product_tmpl_rest_id')
    def onchange_product_tmpl_rest_id(self):
        return {'domain': {'product_id': [('product_tmpl_id', '=', self.product_tmpl_rest_id.id)]}}

    def change_quality_pass(self):
        self.status = 'pass'
        if not self.productivity_id.quality_restriction_ids.filtered(lambda r: r.status == 'pending'):
            self.productivity_id.qty_status = 'quality_restriction'
        return self.reload()

    def change_quality_fail(self):
        self.status = 'fail'
        if not self.productivity_id.quality_restriction_ids.filtered(lambda r: r.status == 'pending'):
            self.productivity_id.qty_status = 'quality_restriction'
        return self.reload()

    def reload(self):
        return {
            'type': 'ir.actions.act_window',
            'res_id': self.productivity_id.id,
            'res_model': 'mrp.workcenter.productivity',
            'target': 'new',
            'name': 'Quality Restrictions//small',
            'views': [(self.env.ref('aci_estimation.mrp_workcenter_productivity_quality_restriction_form').id, 'form')]
        }


class MrpWorkcenterProductivityLossInherit(models.Model):
    _inherit = "mrp.workcenter.productivity.loss.type"

    loss_type = fields.Selection(selection_add=[('unproductive', 'Unproductive'), ('leave', 'Leave')],
                                 ondelete={'unproductive': 'cascade', 'leave': 'cascade'})


class MrpWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'
    _order = 'final_start_date desc'

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if 'pay_amount' in fields:
            fields.remove('pay_amount')
        res = super(MrpWorkcenterProductivity, self).read_group(domain, fields, groupby, offset=offset, limit=limit,
                                                               orderby=orderby, lazy=lazy)
        return res

    input_category = fields.Selection([('add', 'Add'), ('adjust_plus', 'Adjust +'), ('adjust_minus', 'Adjust -')], default='add')
    input_type = fields.Selection([('qty', 'Qty'), ('progress', 'Progress'), ('check', 'Check')], default='qty')
    timetracking_id = fields.Many2one('mrp.timetracking', string='TimeTracking ID', ondelete='restrict')
    restriction_ids = fields.Many2many('mail.activity', 'mrp_productivity_activity_rel', 'productivity_id', 'activity_id')
    step_id = fields.Many2one('lbm.work.order.step', string='Step')
    resource_id = fields.Many2one('mrp.workcenter', 'Workcenter')
    is_productivity = fields.Boolean()
    duration = fields.Float('Duration', compute='_compute_duration', store=True)
    worked_duration = fields.Float(string='H/H')
    worked_rate = fields.Float(compute='_compute_worked_rate')
    manual = fields.Boolean(related='loss_id.manual', store=True, readonly=True)

    offset_start_date = fields.Datetime('Offset St. Date')
    offset_end_date = fields.Datetime('Offset End Date')
    final_start_date = fields.Datetime('Final St. Date', compute='_compute_final_start_date', store=True)
    final_end_date = fields.Datetime('Final End Date', compute='_compute_final_end_date', store=True)

    # New fields
    forecast = fields.Boolean(string='Prestimation')
    prestim = fields.Selection([('normal', 'Normal'), ('prestimated', 'Prestimated')], compute='_compute_prestim', store=True)
    available = fields.Boolean(default='True')
    qty_progress = fields.Float('Qty. Progress', default=0)
    qty_operators = fields.Integer('Qty. Operators')
    rate_uom = fields.Many2one('uom.uom', string='Rate UoM',
        compute='_compute_rate_data', store=True)

    estimation_id = fields.Many2one('mrp.estimation', ondelete='restrict')
    qty_status = fields.Selection([('pending', 'Pending'),
                                   ('waiting_approval', 'Waiting approval'),
                                   ('quality_restriction', 'Quality approved'),
                                   ('approved', 'Cost Approved')
                                   ], default='pending')
    note = fields.Text(string='Notes')
    key = fields.Char(string='Key')
    key_diff = fields.Char(string='Key_diff')
    type = fields.Selection([
                ('manual', 'Manual Values'),
                ('default', 'Default Values'),
                ('automatic', 'Default Values by Checkout (Calendar Trigger)'),
                ('automatic_manual', 'Default Values by Checkout (Manual Trigger)'),
                ('automatic_systray', 'Default Values by Checkout (Systray Trigger)')
            ], default='default', required=True)
    step_categ = fields.Many2one(related='step_id.workstep_id.categ_id', string='Category', store=True)
    employee_id = fields.Many2one('hr.employee')
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    tracking_origin = fields.Selection([
        ('step', 'Step'),
        ('workorder', 'WorkOrder'),
        ('activity', 'Activity')], default='step', required=True)
    employee_ids = fields.Many2many('hr.employee')
    # Todo: Check which variables are still needed
    type_analytic = fields.Boolean(compute='_compute_activity_data_bom', store=True)
    type_qty = fields.Boolean(compute='_compute_activity_data_bom', store=True)
    product_id = fields.Many2one('product.product', compute='_compute_activity_data_bom', store=True)
    attr_id = fields.Many2many(related='step_id.product_id.attribute_value_ids', readonly=True)
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic id', ondelete='restrict')
    analytic_name = fields.Char(related='analytic_id.name', string='Analytic')
    accum_times = fields.Float(string="End Date")
    step_type = fields.Selection(related='step_id.product_id.step_type', string='Type Qty')
    qty_manual = fields.Float(default=0)
    progress = fields.Float(compute='_compute_progress', string='% Progress')
    wo_qty_progress = fields.Float(compute='_compute_wo_qty_progress', store=True)
    # GEOLOCATION VARIABLES
    ip = fields.Char('IP')
    device = fields.Char('Device')
    os = fields.Char('OS')
    latitude = fields.Float('Latitude')
    longitude = fields.Float('Longitude')
    geolocation_message = fields.Char('Geolocation Message')
    imputed_by_employee_id = fields.Many2one('hr.employee', string='Imputed by Employee')
    wkcenter = fields.Many2one(related='step_id.wkcenter')
    workorder_by_step = fields.Many2one('mrp.workorder', compute='_compute_workorder_by_step', string='Workorder ID', store=True, compute_sudo=True)
    warehouse_id = fields.Many2one(related='workorder_by_step.warehouse_id')
    baseline_id = fields.Many2one(related='workorder_by_step.baseline_id')
    product_tmpl_wo_id = fields.Many2one('product.template', compute='_compute_product', string='Workorder', store=True)
    party_id = fields.Many2one(related='workorder_by_step.product_wo.party_id', store=True)
    product_tmpl_step_id = fields.Many2one('product.template', compute='_compute_product', string='Step', store=True)
    version = fields.Integer(related='workorder_by_step.operation_id.version')
    product_model = fields.Char(related='workorder_by_step.product_id.name', string='Mod.')
    production_by_step = fields.Many2one('mrp.production', compute='_compute_workorder_by_step',
                                         string='Manufacturing Order', store=False, compute_sudo=True)
    period_id = fields.Many2one('payment.period', "Period", ondelete='restrict')
    pay_amount = fields.Float('P. A.')
    total_pay_amount = fields.Float('T.P.A.', compute='_compute_total_pay_amount', store=True)
    workorder_extra = fields.Float(related='workorder_by_step.operation_extra')
    workorder_extra_available = fields.Float(related='workorder_by_step.operation_extra_available')
    operation_extra = fields.Float('Extra')
    total_operation_extra = fields.Float('T.E.', compute='_compute_total_operation_extra', store=True)
    partial_amount = fields.Float('Part.', compute='_compute_partial_amount', store=True)
    discount = fields.Float('Dis.')
    discount_amount = fields.Float('T.Dis.', compute='_compute_discount_amount', store=True)
    percentage_discount = fields.Float('%Dis.', compute='_compute_discount', store=True)
    deposit = fields.Float('War.')
    percentage_deposit = fields.Float('%War.', compute='_compute_deposit', store=True)
    total_cost = fields.Float('T.C.', compute='_compute_total_cost', store=True)
    input_ids = fields.One2many('mrp.timetracking.input', 'productivity_id')
    discount_validated = fields.Boolean(default=False)
    warranty_validated = fields.Boolean(default=False)
    quality_restriction_ids = fields.One2many('mrp.workcenter.productivity.quality', 'productivity_id', string='Quality Restrictions')
    quality_restriction_qty = fields.Integer(compute='_compute_quality_restriction_qty')

    def write(self, vals):
        if 'offset_end_date' in vals.keys():
            for _id in self:
                if _id.tracking_origin == 'step' and not _id.workorder_id:
                    wo_tracking_id = self.env['mrp.workcenter.productivity'].search([('key', '=', _id.key),
                                                                                     ('id', '!=', _id.id)])
                    wo_tracking_id.write({'offset_end_date': vals.get('offset_end_date')})
        if 'offset_start_date' in vals.keys():
            for _id in self:
                if _id.tracking_origin == 'step' and not _id.workorder_id:
                    wo_tracking_id = self.env['mrp.workcenter.productivity'].search([('key', '=', _id.key),
                                                                                     ('id', '!=', _id.id)])
                    wo_tracking_id.write({'offset_start_date': vals.get('offset_start_date')})
        return super(MrpWorkcenterProductivity, self).write(vals)

    @api.model
    def create(self, vals):
        res = super(MrpWorkcenterProductivity, self).create(vals)
        estimation_ids = self.env['mrp.estimation'].search([('workcenter_id', 'in', res.mapped('resource_id').ids),
                                                            ('estimation_type', '=', 'period'),
                                                            ('start_period', '<=', res.final_start_date),
                                                            ('end_period', '>=', res.final_start_date),
                                                            ('warehouse_id', '>=', res.timetracking_id.warehouse_id.id)])

        if estimation_ids:
            for estimation_id in estimation_ids:
                if not estimation_id.period_status or estimation_id.period_status in ('draft', 'open'):
                    estimation_id.update_tracking_btn()
                else:
                    raise ValidationError("The estimation is not open anymore.")
            res['estimation_id'] = estimation_ids[0].id

        input_ids = self.env['mrp.workcenter.productivity'].search([('workorder_id', '=', res.workorder_by_step.id)])
        if not res.workorder_by_step.production_id.bom_id.type_qty\
                and res.workorder_by_step.qty_production < res.wo_qty_progress + sum(input_ids.mapped('wo_qty_progress')):
            raise ValidationError("You have exceeded the maximum qty: \n"
                                  "WorkOrder Maximun = {}\n"
                                  "Wanted Input (WO) = {}\n"
                                  "Accumulated = {}\n\n"
                                  "WorkOrder {}".format(res.workorder_by_step.qty_production,
                                                            res.wo_qty_progress,
                                                            sum(input_ids.mapped('wo_qty_progress'))))

        if res.workorder_by_step.quality_restriction:
            res['quality_restriction_ids'] = [(0, False, {'product_tmpl_rest_id': qr.product_tmpl_rest_id.id,
                                                          'product_id': qr.product_id.id}) for qr in res.workorder_by_step.product_wo.quality_restriction_ids]
        return res

    @api.constrains('duration')
    def _check_duration(self):
        for _id in self:
            if _id.duration:
                if _id.duration <= 0:
                    raise ValidationError("The tracking {} has a negative duration ({}).".format(_id.id, _id.duration))

    @api.constrains('final_end_date')
    def _check_end(self):
        for _id in self:
            if _id.final_start_date and _id.final_end_date:
                start = _id.final_start_date
                end = _id.final_end_date
                tz_start = self.env['time.tracking.actions'].get_tz_datetime(start, _id.employee_id.user_id)
                tz_end = self.env['time.tracking.actions'].get_tz_datetime(end, _id.employee_id.user_id)
                # if tz_start.weekday() != tz_end.weekday():
                #     raise ValidationError("The tracking {} can not start and end in a different day.".format(_id.id))

    @api.constrains('offset_end_date')
    def _check_offset_end(self):
        Blocks = self.env['hr.productivity.block']
        Tracking = self.env['mrp.workcenter.productivity']
        for _id in self:
            if _id.offset_end_date:
                if _id.tracking_origin == 'workorder' or (_id.tracking_origin == 'step' and not _id.workorder_id):
                    extra_args = ('resource_id', '=', _id.resource_id.id) if _id.tracking_origin == 'workorder' \
                        else ('workorder_id', '=', None)
                    block_id = Blocks.search([('employee_id', '=', _id.resource_id.employee_id.id),
                                              ('final_start_date', '<=', _id.final_start_date),
                                              ('final_end_date', '>=', _id.final_start_date)])
                    if block_id:
                        if _id.offset_end_date > block_id.final_end_date:
                            raise ValidationError("Offset is bigger than end of block")
                    tracking_ids = Tracking.search([('resource_id', '=', _id.resource_id.id),
                                                    ('final_start_date', '<', _id.offset_end_date),
                                                    ('final_end_date', '>', _id.offset_end_date),
                                                    ('id', '!=', _id.id), extra_args]).ids
                    consumed_tracking_ids = Tracking.search([('resource_id', '=', _id.resource_id.id),
                                                    ('final_start_date', '>=', _id.final_start_date),
                                                    ('final_end_date', '<=', _id.offset_end_date),
                                                    ('id', '!=', _id.id), extra_args]).ids
                    working_tracking_ids = Tracking.search([('resource_id', '=', _id.resource_id.id),
                                                            ('final_start_date', '<', _id.offset_end_date),
                                                            ('final_end_date', '=', None),
                                                            ('id', '!=', _id.id), extra_args]).ids
                    if tracking_ids or consumed_tracking_ids or working_tracking_ids:
                        raise ValidationError("Tracking {} overlaps with tracking {}{}{}".format(_id.id, tracking_ids,
                                                                                                 consumed_tracking_ids,
                                                                                                 working_tracking_ids))

    @api.constrains('offset_start_date')
    def _check_offset_start(self):
        Blocks = self.env['hr.productivity.block']
        Tracking = self.env['mrp.workcenter.productivity']
        for _id in self:
            if _id.offset_start_date:
                if _id.tracking_origin == 'workorder' or (_id.tracking_origin == 'step' and not _id.workorder_id):
                    extra_args = ('resource_id', '=', _id.resource_id.id) if _id.tracking_origin == 'workorder' \
                        else ('workorder_id', '=', None)
                    block_id = Blocks.search([('employee_id', '=', _id.resource_id.employee_id.id),
                                              ('final_start_date', '<=', _id.final_end_date),
                                              ('final_end_date', '>=', _id.final_end_date)])
                    if block_id:
                        if _id.offset_start_date < block_id.final_start_date:
                            raise ValidationError("Offset is smaller than start of block")
                    tracking_ids = Tracking.search([('resource_id', '=', _id.resource_id.id),
                                                    ('final_start_date', '<=', _id.offset_start_date),
                                                    ('final_end_date', '>', _id.offset_start_date),
                                                    ('id', '!=', _id.id), extra_args]).ids
                    consumed_tracking_ids = Tracking.search([('resource_id', '=', _id.resource_id.id),
                                                    ('final_start_date', '>=', _id.offset_start_date),
                                                    ('final_end_date', '<=', _id.final_end_date),
                                                    ('id', '!=', _id.id), extra_args]).ids
                    if tracking_ids or consumed_tracking_ids:
                        raise ValidationError("Tracking {} overlaps with tracking {}{}".format(_id.id, tracking_ids,
                                                                                           consumed_tracking_ids))

    @api.depends('quality_restriction_ids')
    def _compute_quality_restriction_qty(self):
        for r in self:
            r.quality_restriction_qty = len(r.quality_restriction_ids)

    @api.depends('tracking_origin', 'step_id', 'workorder_id')
    def _compute_workorder_by_step(self):
        for r in self:
            if r.tracking_origin == 'step':
                r.workorder_by_step = r.step_id.workorder_id.id
            else:
                r.workorder_by_step = r.workorder_id.id
            r.production_by_step = r.workorder_by_step.production_id.id

    @api.depends('step_id', 'workorder_by_step')
    def _compute_product(self):
        for r in self:
            r.product_tmpl_wo_id = r.workorder_by_step.product_wo.product_tmpl_id.id
            r.product_tmpl_step_id = r.step_id.product_id.product_tmpl_id.id

    @api.depends('pay_amount', 'wo_qty_progress', 'workorder_by_step')
    def _compute_total_pay_amount(self):
        for r in self:
            r.total_pay_amount = r.wo_qty_progress * r.pay_amount / r.workorder_by_step.qty_production \
                if r.workorder_by_step.qty_production else 0

    @api.depends('operation_extra', 'wo_qty_progress', 'workorder_by_step')
    def _compute_total_operation_extra(self):
        for r in self:
            r.total_operation_extra = r.wo_qty_progress * r.operation_extra / r.workorder_by_step.qty_production \
                if r.workorder_by_step.qty_production else 0

    @api.depends('total_operation_extra', 'total_pay_amount')
    def _compute_partial_amount(self):
        for r in self:
            r.partial_amount = r.total_operation_extra + r.total_pay_amount

    @api.depends('deposit', 'total_operation_extra', 'total_pay_amount', 'discount')
    def _compute_deposit(self):
        for r in self:
            subtotal = r.total_operation_extra + r.total_pay_amount - r.discount
            r.percentage_deposit = r.deposit * 100 / subtotal if subtotal > 0 else 0

    @api.depends('partial_amount', 'discount')
    def _compute_discount_amount(self):
        for r in self:
            r.discount_amount = r.partial_amount - r.discount

    @api.depends('discount', 'total_operation_extra', 'total_pay_amount')
    def _compute_discount(self):
        for r in self:
            subtotal = r.total_operation_extra + r.total_pay_amount
            r.percentage_discount = r.discount * 100 / subtotal if subtotal > 0 else 0

    @api.depends('total_operation_extra', 'total_pay_amount', 'discount', 'deposit')
    def _compute_total_cost(self):
        for r in self:
            r.total_cost = r.total_operation_extra + r.total_pay_amount - r.discount - r.deposit

    @api.depends('workorder_id', 'step_id', 'workorder_id.production_id.bom_id.type_qty',
                 'step_id.production_id.bom_id.type_qty')
    def _compute_activity_data_bom(self):
        for _id in self:
            if _id.workorder_id:
                _id.type_analytic = _id.workorder_id.production_id.bom_id.type_analytic
                _id.type_qty = _id.workorder_id.production_id.bom_id.type_qty
                _id.product_id = _id.workorder_id.product_wo.id

            elif _id.step_id:
                _id.type_analytic = _id.step_id.production_id.bom_id.type_analytic
                _id.type_qty = _id.step_id.production_id.bom_id.type_qty
                _id.product_id = _id.step_id.product_id.id

    @api.depends('workorder_id', 'step_id')
    def _compute_production_id(self):
        for _id in self:
            if _id.workorder_id:
                _id.production_id = _id.workorder_id.production_id.id
            elif _id.step_id:
                _id.production_id = _id.step_id.production_id.id

    @api.depends('input_ids')
    def _compute_duration(self):
        for r in self:
            r.duration = sum(r.input_ids.mapped('duration'))

    @api.depends('date_start', 'offset_start_date')
    def _compute_final_start_date(self):
        for _id in self:
            if _id.date_start:
                final_date = _id.date_start
                if _id.offset_start_date:
                    final_date = _id.offset_start_date
                _id.final_start_date = final_date

    @api.depends('date_end', 'offset_end_date')
    def _compute_final_end_date(self):
        for _id in self:
            if _id.date_end:
                final_date = _id.date_end
                if _id.offset_end_date:
                    final_date = _id.offset_end_date
                _id.final_end_date = final_date

    @api.depends('forecast')
    def _compute_prestim(self):
        for r in self:
            r.prestim = 'prestimated' if r.forecast else 'normal'

    @api.depends('step_id')
    def _compute_rate_data(self):
        for _id in self:
            if _id.step_id:
                _id.rate_uom = _id.step_id.rate_uom.id

    @api.depends('tracking_origin', 'step_id', 'workorder_id', 'qty_progress')
    def _compute_progress(self):
        for _id in self:
            if _id.tracking_origin == 'step':
                _id.progress = round(_id.qty_progress * 100 / _id.step_id.product_qty, 2) if _id.step_id.product_qty else 0
            elif _id.tracking_origin == 'workorder':
                _id.progress = round(_id.qty_progress * 100 / _id.workorder_id.qty_production, 2) if _id.workorder_id.qty_production else 0
            else:
                _id.progress = 0

    @api.depends('tracking_origin', 'qty_progress', 'step_id', 'workorder_id')
    def _compute_wo_qty_progress(self):
        for _id in self:
            if _id.tracking_origin == 'step' and _id.timetracking_id:
                wo_progress = _id.timetracking_id.step_id.tracking_ratio * _id.timetracking_id.workorder_id.qty_production
                _id.wo_qty_progress = _id.qty_progress * wo_progress / _id.timetracking_id.step_id.product_qty if _id.timetracking_id.step_id.product_qty > 0 else 0
            elif _id.tracking_origin == 'workorder' and _id.timetracking_id:
                _id.wo_qty_progress = _id.qty_progress
            else:
                _id.wo_qty_progress = 0

    @api.depends('worked_duration', 'qty_operators', 'qty_progress')
    def _compute_worked_rate(self):
        for _id in self:
            _id.worked_rate = _id.qty_operators * _id.worked_duration / _id.qty_progress if _id.qty_progress else 0

    def show_quality_restriction(self):
        return {
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'res_model': 'mrp.workcenter.productivity',
            'target': 'new',
            'name': 'Quality Restrictions//small',
            'views': [(self.env.ref('aci_estimation.mrp_workcenter_productivity_quality_restriction_form').id, 'form')]
        }

    def open_form(self):
        return {
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'res_model': 'mrp.workcenter.productivity',
            'target': 'current',
            'views': [(self.env.ref('aci_estimation.detail_workcenter_productivity_form_inherit_view').id, 'form')],
        }

    def button_block(self):
        self.ensure_one()
        # self.workcenter_id.order_ids.end_all()
        ModelData = self.env['ir.model.data']
        stage_blocked = ModelData.get_object(
            'aci_estimation', 'aci_blocked_stage')

        if self.workorder_id:
            wo_id = self.workorder_id
            wo_id.stage_id = stage_blocked.id
            wo_id.end_all()
            if wo_id.manage_type == 'step':
                self.block_step_lines(wo_id)
        elif self.step_id:
            self.block_step(self.step_id)

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def button_delete_tracking(self):
        stage_id = self.env['time.tracking.actions'].get_stage_id('ToDo')
        _ids = self.search([('key', '=', self.key)])
        _field = 'step_id' if self.tracking_origin == 'step' else 'workorder_id'
        _ids.mapped(_field).write({'stage_id': stage_id})
        _ids.unlink()

    def button_show_track_detail(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'detail_workcenter_productivity_form_view')
        return {
            'name': _('Time Tracking Detail Kanban'),
            'res_model': 'mrp.workcenter.productivity',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'current'
        }

    def block_step_lines(self, wo):
        self.ensure_one()
        ModelData = self.env['ir.model.data']
        stage_working = ModelData.get_object(
            'aci_estimation', 'aci_working_stage')

        for step_id in wo.step_ids.filtered(lambda r: r.stage_id.id == stage_working.id):
            self.create({
                'step_id': step_id.id,
                'loss_id': self.loss_id.id,
                'workcenter_id': step_id.workorder_id.workcenter_id.id,
                'description': self.description
            })
            self.block_step(step_id)

    def block_step(self, step):
        self.ensure_one()
        ModelData = self.env['ir.model.data']
        stage_blocked = ModelData.get_object(
            'aci_estimation', 'aci_blocked_stage')

        step.stage_id = stage_blocked.id
        step.end_all()

    def calc_enddate_with_schedule(self, calendar_id, enddate):
        self.ensure_one()
        weekday = enddate.weekday()
        schedule_map = calendar_id.get_schedule_map()
        if weekday in schedule_map.keys():
            max_hour = max(map(lambda r: r[1]['end'], schedule_map[weekday]['ranges'].items()))
            if enddate.hour > max_hour:
                maxdate = enddate.replace(hour=max_hour)
                self.write({'date_end': maxdate})
                loss_id = self.env['mrp.workcenter.productivity.loss'].search([('name', '=', 'Out-Of-Schedule Work')], limit=1)
                if not len(loss_id):
                    raise UserError(_("You need to define at least one unactive productivity loss to 'Out-Of-Schedule Work'. Create one from the Manufacturing app, menu: Configuration / Productivity Losses."))
                self.copy({'date_start': maxdate, 'date_end': enddate, 'loss_id': loss_id.id})
                return 'done'
        self.write({'date_end': enddate})

    def adjust_tracking_dates(self):
        for _id in self:
            if _id.offset_start_date:
                _id.final_start_date = _id.offset_start_date
            elif _id.date_start:
                _id.final_start_date = _id.date_start

            if _id.offset_end_date:
                _id.final_end_date = _id.offset_end_date
            elif _id.date_end:
                _id.final_end_date = _id.date_end

    def _get_tz_datetime(self, datetime, user_id):
        Params = self.env['ir.config_parameter']
        tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
        tz = Params.get_param('tz') if tz_param else None
        if tz:
            tz_datetime = datetime.astimezone(pytz.timezone(str(tz)))
        else:
            user_id = user_id if user_id else self.env.user
            tz_datetime = datetime.astimezone(pytz.timezone(str(user_id.tz)))
        return tz_datetime

    # CHECK IN/ CHECK OUT VALIDATIONS !!
    def automatic_checkout(self):
        date = datetime.datetime.now()

        open_attendance = self.env['hr.attendance'].search([('check_out', '=', False)])
        for attendance in open_attendance:
            current_date = self._get_tz_datetime(date, attendance.employee_id.user_id)

            current_date_days = current_date.strftime("%Y-%m-%d")
            reference_hour = self._get_float_hour(current_date)

            contract_id = self.env['hr.contract'].search([('employee_id', '=', attendance.employee_id.id)], limit=1)
            if contract_id.tolerance == 'restrictive':

                checkIn_utc = attendance.check_in
                reference_date = self._get_tz_datetime(checkIn_utc, attendance.employee_id.user_id)

                reference_date_days = reference_date.strftime("%Y-%m-%d")
                weekday = reference_date.weekday()
                if current_date_days > reference_date_days:
                    reference_hour = 23.59
                tolerance_time = int(contract_id.tolerance_time / 60) + (contract_id.tolerance_time % 60)/100

                attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                    .filtered(lambda r: int(r.dayofweek) == int(weekday) and self.hour_time(r.hour_to + tolerance_time) < reference_hour)

                if attendance_ids:
                    checkIn_utc = attendance.check_in
                    attendance_date = self._get_tz_datetime(checkIn_utc, attendance.employee_id.user_id)

                    attendance_reference_hour = self._get_float_hour(attendance_date)

                    check_out_hour = 0
                    for att in attendance_ids:
                        check_out_hour = att.hour_to if att.hour_to > check_out_hour else check_out_hour
                    hour = int('{0:02.0f}'.format(*divmod(check_out_hour * 60, 60)))
                    minutes = int('{1:02.0f}'.format(*divmod(check_out_hour * 60, 60)))
                    check_out_date = reference_date.replace(hour=hour, minute=minutes)

                    tz_name = self._context.get('tz') or self.env.user.tz
                    tz = tz_name and pytz.timezone(tz_name) or pytz.UTC
                    utc_check_out_date = tz.localize(check_out_date.replace(tzinfo=None), is_dst=False).astimezone(pytz.UTC).replace(tzinfo=None)
                    if attendance_reference_hour < check_out_hour:
                        tracking_end = self.env['mrp.workcenter.productivity'].search([
                            ('employee_id', '=', attendance.employee_id.id), ('workorder_id', '=', False)], order='final_end_date DESC',
                            limit=1)
                        if tracking_end:
                            if tracking_end.final_end_date:
                                utc_check_out_date = tracking_end.final_end_date
                            else:
                                utc_check_out_date = tracking_end.final_start_date

                        attendance.write({'check_out': utc_check_out_date})
        return True

    def _convert_float_to_date(self, reference_date=None, float_date=None):
        hour = int('{0:02.0f}'.format(*divmod(float_date * 60, 60)))
        minutes = int('{1:02.0f}'.format(*divmod(float_date * 60, 60)))
        return reference_date.replace(hour=hour, minute=minutes, second=0)

    @api.model
    def hour_time(self, time):
        time = round(time, 2)
        hour = int(time)
        minutes = time - hour
        hour = hour + int(minutes * 100 / 60)
        minutes = (minutes * 100) % 60 / 100
        return round(hour + minutes, 2)

    # aci_estimation/RESOURCE.PY METHODS: Todo. Check results
    @api.model
    def _get_float_hour(self, date):
        return float('{0}.{1}'.format(date.hour, date.minute))

    @api.model
    def _get_date_object(self, date):
        return self._get_date_tz(date)

    @api.model
    def _get_date_tz(self, date):
        timezone = fields.Datetime.context_timestamp(self, timestamp=datetime.datetime.now()).tzinfo
        return pytz.UTC.localize(date).astimezone(timezone)

    def restore_step_stage(self, restore_type=None):
        # Get all the steps that are currently on working
        open_attendance = self.env['hr.attendance'].search([('check_out', '=', False)])
        employee_ids = open_attendance.mapped('employee_id')
        working_employee_ids = [employee.id for employee in employee_ids]

        remove_employee = []
        for employee_id in employee_ids:
            active_step = self.env['mrp.workcenter.productivity'].search([('step_id.wkcenter.employee_id', '=', employee_id.id),
                                                                          ('date_end', '=', False)], limit=1)
            valid_activity = self.validate_activity(active_step.key)
            if not valid_activity:
                remove_employee.append(employee_id.id)

        valid_employee_ids = list(set(working_employee_ids) - set(remove_employee))
        working_step = self.env['mrp.workcenter.productivity'].search([('date_end', '=', False),
                                                                       ('workorder_id', '=', False),
                                                                       ('step_id.wkcenter.employee_id', 'not in', valid_employee_ids)])

        if working_step:
            step_data = []
            prod_by_key = {}
            prod_by_wc = {}
            taken_wo = []   # Since in multistep key_diff is the same in all the steps, I need to validate if I already used that wo
            # Get elements and quantity by key
            for step in working_step:
                working_wo = self.env['mrp.workcenter.productivity'].search([('key_diff', '=', step.key_diff),
                                                                             ('step_id', '=', False)])
                valid_working_wo = working_wo
                if len(working_wo) > 1:
                    found_wo = False
                    for wo in working_wo:
                        if not found_wo and wo.id not in taken_wo:
                            valid_working_wo = wo
                            taken_wo.append(wo.id)
                            found_wo = True
                step_data.append([step, valid_working_wo, step.key, step.step_id.wkcenter.id])
                prod_by_key.update(
                    {step.key: prod_by_key[step.key] + 1}) if step.key in prod_by_key else prod_by_key.update({step.key: 1})
                prod_by_wc.update(
                    {step.step_id.wkcenter.id: prod_by_wc[step.step_id.wkcenter.id] + 1}) if step.step_id.wkcenter.id in prod_by_wc else prod_by_wc.update({step.step_id.wkcenter.id: 1})

            # Calculate dateEnd by key (first check_out is priority)
            wc_check_out_date = {}
            key_check_out_date = {}
            for step in working_step:
                attendance = self.env['hr.attendance'].search(
                    [('employee_id', '=', step.step_id.wkcenter.employee_id.id)], order='check_in DESC')
                last_attendance = attendance[0] if attendance[0].check_out else False
                if last_attendance:
                    formated_check_out = last_attendance.check_out
                    wc_check_out_date.update({step.step_id.wkcenter.id: formated_check_out})

                if step.key not in key_check_out_date:
                    productivity = self.env['mrp.workcenter.productivity'].search([('key', '=', step.key),
                                                                                   ('workorder_id', '=', False)])

                    date_end = datetime.datetime.now()
                    for prod in productivity:
                        workcenter_id = prod.step_id.wkcenter.id
                        if workcenter_id in wc_check_out_date:
                            date_end = wc_check_out_date[workcenter_id] if wc_check_out_date[workcenter_id] < date_end else date_end
                    key_check_out_date.update({step.key: date_end})

            # Calculate durations by wc (in seconds)
            duration_by_wc = {}
            for step in working_step:
                if step.step_id.wkcenter.id not in duration_by_wc:
                    duration = key_check_out_date[step.key] - step.date_start
                    duration_hours = duration.total_seconds()
                    duration_by_wc.update({step.step_id.wkcenter.id: duration_hours / prod_by_wc[step.step_id.wkcenter.id]})

            # Calculate QTY progress by step ID
            qty_progress = {}
            for step in working_step:
                if step.step_id.id not in qty_progress:
                    # qty_ids = self.env['mrp.workcenter.productivity'].search([('step_id', '=', step.id)])
                    qty_calc = sum(step.step_id.timesheet_ids.filtered(lambda r: r.step_id.id != step.step_id.id).mapped('final_calc'))
                    duration_by_wkcenter = duration_by_wc[step.step_id.wkcenter.id] / 3600

                    qty = step.step_id.rate * duration_by_wkcenter
                    product_type = step.step_id.product_id.step_type
                    if product_type == 'unit':
                        qty = 1
                    elif product_type == 'integer':
                        qty = int(qty) if int(qty) != 0 else 1

                    if step.step_id.production_id.bom_id.type_qty is False:
                        if qty_calc + qty > step.step_id.product_qty:
                            qty = step.step_id.product_qty - qty_calc
                            if product_type == 'unit':
                                qty = 1
                            elif product_type == 'integer':
                                qty = int(qty)
                    if duration_by_wkcenter == 0:
                        qty_progress.update({step.step_id.id: 0})
                    else:
                        qty_progress.update({step.step_id.id: qty})

            # STEP DATA
            # [0] PRODUCTIVITY STEP
            # [1] PRODUCTIVITY WORKORDER
            # [2] KEY
            # [3] WORKCENTER
            step_data.sort(key=lambda x: (x[2], x[3]))
            current_key = 'START'
            current_wc = 0
            stage_id = self.env['mrp.timetracking.stage'].search([('name', '=', 'ToDo')])
            for data in step_data:
                date_start = data[0].date_start if current_wc != data[3] else date_start + dateutil.relativedelta.relativedelta(seconds=duration_by_wc[data[0].step_id.wkcenter.id])
                calculated_date_end = date_start + dateutil.relativedelta.relativedelta(seconds=duration_by_wc[data[0].step_id.wkcenter.id])
                if date_start >= calculated_date_end:
                    # Something is wrong ...
                    calculated_date_end = date_start
                # Validating type of record ..
                if restore_type == 'manual':
                    type = 'automatic_manual'
                elif restore_type == 'calendar':
                    type = 'automatic'
                else:
                    type = 'automatic_systray'

                data[0].write({'date_start': date_start,
                               'date_end': calculated_date_end,
                               'qty_operators': data[0].step_id.min_members,
                               'qty_manual': qty_progress[data[0].step_id.id],
                               'progress': 100,
                               'qty_progress': qty_progress[data[0].step_id.id],
                               'type': type})
                data[1].write({'date_start': date_start,
                               'date_end': calculated_date_end,
                               'qty_operators': data[0].step_id.min_members,
                               'qty_manual': qty_progress[data[0].step_id.id],
                               'progress': 100,
                               'qty_progress': qty_progress[data[0].step_id.id],
                               'type': type})
                data[0].step_id.write({'stage_id': stage_id.id})
                current_wc = data[3]
                self.delete_work_block(data[0].step_id.id)

    def validate_activity(self, key):
        steps = self.env['mrp.workcenter.productivity'].search([('key', '=', key),
                                                                ('workorder_id', '=', False)])
        valid_activity = True
        for step in steps:
            if not self.has_check_in(step.step_id.wkcenter):
                valid_activity = False
        return valid_activity

    def has_check_in(self, workcenter_id):

        if not workcenter_id.employee_id.id:
            return False

        attendance = self.env['hr.attendance'].search([('check_out', '=', False),
                                                       ('employee_id', '=', workcenter_id.employee_id.id)])
        if not attendance:
            return False
        return True

    def update_pay_amount_btn(self, context=None):
        context = self.env.context
        for input_id in self.browse(context.get('active_ids')).filtered(lambda r: r.qty_status != 'approved' and
                                                                        r.discount_validated is False):
            input_id.pay_amount = input_id.workorder_by_step.direct_cost

    def open_analytic_form(self):
        view_id = self.env['ir.model.data'].get_object(
            'analytic', 'view_account_analytic_account_form')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'res_model': 'account.analytic.account',
            'name': '{}'.format(self.analytic_name),
            'target': 'current',
            'res_id': self.analytic_id.id
        }

    def close_wo_wc_btn(self, context=None):
        context = self.env.context
        input_ids = self.browse(context.get('active_ids'))
        for input_id in input_ids:
            timetracking_ids = self.env['mrp.timetracking'].search([('workorder_id', '=', input_id.timetracking_id.workorder_id.id),
                                                                    ('workcenter_id', '=', input_id.timetracking_id.workcenter_id.id)])

            timetracking_ids.write({'available': False})

    def set_approve_btn(self, context=None):
        if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
            raise ValidationError(_('You are not allowed to do this process'))
        context = self.env.context

        if self.browse(context.get('active_ids')).filtered(lambda r: r.workorder_by_step.quality_restriction is True \
                                                                     and r.qty_status != 'quality_restriction'):
            raise ValidationError(_('Approve quality restrictions'))

        for input_id in self.browse(context.get('active_ids')).filtered(lambda r: r.available is True):
            input_id.qty_status = 'approved'

    def show_input_btn(self):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree')],
            'res_model': 'mrp.timetracking.input',
            'name': 'Detail',
            'target': 'new',
            'domain': [('id', 'in', self.input_ids.ids)]
        }

    def block_input_btn(self):
        context = self.env.context
        self.browse(context.get('active_ids')).write({'available': False})

    def open_input_btn(self):
        if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
            raise ValidationError(_('You are not allowed to do this process'))
        context = self.env.context
        self.browse(context.get('active_ids')).write({'available': False})
