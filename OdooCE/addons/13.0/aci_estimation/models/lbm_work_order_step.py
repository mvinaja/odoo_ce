# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta

class LbmWorkOrderStep(models.Model):
    _name = 'lbm.work.order.step'
    _description = 'lbm.work.order.step'
    _inherit = ['mail.activity.mixin', 'mail.thread']
    _rec_name = 'product_id'

    def _get_default_stage_id(self):
        Stage = self.env['mrp.timetracking.stage']
        stage_id = Stage.search([('name', '=', 'ToDo')], limit=1)
        return stage_id.id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        stage_ids = stages._search([])
        return stages.browse(stage_ids)

    # Direct Cost
    sequence = fields.Integer()
    net_cost = fields.Float('Labor Cost', default=0)
    extra_cost = fields.Float('Extra Cost', default=0)
    ratio = fields.Float('Ratio', default=0)

    manual = fields.Boolean()
    workstep_id = fields.Many2one('mrp.bom.line', ondelete='set null')

    production_id = fields.Many2one(related='workorder_id.production_id', store=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', ondelete='cascade')
    date_planned = fields.Datetime(related='workorder_id.date_planned_start', store=True)

    prod_tmpl_id = fields.Many2one(related='workorder_id.product_wo', store=True)
    product_id = fields.Many2one('product.product', string='Step')
    tracking_ids = fields.One2many('mrp.workcenter.productivity', 'step_id')
    duration_expected = fields.Float(
        'Duration Expected', compute='_compute_duration_expected')
    accum_time = fields.Float('Duration',
        compute='_compute_accum_duration', default=0)
    stage_id = fields.Many2one('mrp.timetracking.stage',
        group_expand='_read_group_stage_ids', default=_get_default_stage_id)

    wkcenter_template = fields.Many2one(related='workorder_id.workcenter_id', store=True,
        domain=lambda self: [('template_id', '=', False)])
    wkcenter = fields.Many2one('mrp.workcenter', string='Workcenter')
    manage_type = fields.Selection(related='workorder_id.manage_type', store=True)
    warehouse_id = fields.Many2one(related='workorder_id.warehouse_id')
    quality_count = fields.Integer('# Quality Alert', compute='_compute_quality_count')

    # New fields
    rate = fields.Float('Value')
    rate_uom = fields.Many2one('uom.uom', string='Rate UoM')
    time_uom = fields.Many2one('uom.uom', string='Time UoM')
    product_qty = fields.Float('Product Qty.')
    min_members = fields.Integer('Base Qty. Operat.',
        related='workorder_id.min_members', store=True, readonly=True)
    max_members = fields.Integer('Max Members',
        related='workorder_id.max_members', store=True, readonly=True)
    timetracking_ids = fields.One2many('mrp.timetracking', 'step_id')
    has_timetracking = fields.Boolean(compute='_compute_has_timetracking')
    has_tracking = fields.Boolean(compute='_compute_has_tracking')
    percent_complete = fields.Float(compute='_compute_percent_complete')
    percent_wo_complete = fields.Float(compute='_compute_percent_complete', string='WO %')
    full_percent_wo_complete = fields.Float(compute='_compute_percent_complete', string='WO %')
    timetracking_active = fields.Boolean(default=True)
    qty_progress = fields.Float(compute='_compute_qty_progress', string='Exec.')
    available_wo_qty_progress = fields.Float(compute='_compute_qty_progress', string='Av.Qty')
    do_tracking = fields.Boolean(compute='_compute_do_tracking', store=True, readonly=False)
    # Operation amount
    manual_labor = fields.Float('U. L.')

    add_value = fields.Boolean(
        'E. Value', related='product_id.add_value', readonly=True)
    value_factor = fields.Float('E. Factor', default=1.0)
    duration = fields.Float('Duration', compute='_compute_duration')
    tracking_ratio = fields.Float(compute='_compute_tracking_ratio')
    unit_labor = fields.Float('U. C. L.', compute='_compute_workstep_unit')
    unit_extra = fields.Float('U. E.', compute='_compute_workstep_unit')

    labor_cost = fields.Float('C. L.', compute='_compute_workstep_cost')
    extra_cost = fields.Float('I. E.', compute='_compute_workstep_cost')
    pay_amount = fields.Float('P. A.', compute='_compute_workstep_cost')

    crew_amount = fields.Float(
        'Crew Cost', related='workorder_id.operation_id.crew_amount', readonly=True)

    @api.depends('rate', 'product_qty')
    def _compute_duration(self):
        '''Compute workstep duration'''
        for _id in self:
            if _id.rate:
                _id.duration = _id.product_qty / _id.rate
            else:
                _id.duration = 0.0

    @api.depends('duration', 'workorder_id.step_duration', 'product_qty', 'rate')
    def _compute_tracking_ratio(self):
        for _id in self:
            _id.tracking_ratio = _id.duration / _id.workorder_id.step_duration

    @api.depends('rate', 'product_qty')
    def _compute_workstep_unit(self):
        '''Workstep's direct and fasar cost'''
        for _id in self:
            _id.unit_labor = _id.rate and _id.crew_amount / _id.rate or 0
            if _id.add_value:
                _id.unit_extra = (_id.workorder_id.workstep_extra * _id.duration * _id.value_factor) / _id.product_qty
            else:
                _id.unit_extra = 0

    @api.depends('rate', 'product_qty')
    def _compute_workstep_cost(self):
        for _id in self:
            _id.labor_cost = _id.unit_labor * _id.product_qty
            if _id.add_value:
                _id.extra_cost = _id.unit_extra * _id.product_qty
            else:
                _id.extra_cost = 0
            operation_labor = _id.workorder_id.operation_labor
            pay_amount = operation_labor and _id.labor_cost / operation_labor or 0
            _id.pay_amount = _id.workorder_id.direct_cost * pay_amount

    def write(self, vals):
        res = super(LbmWorkOrderStep, self).write(vals)
        for _id in self:
            if _id.tracking_ratio * 100 < _id.full_percent_wo_complete:
                raise ValidationError(_('Tracking Ratio can not be lower than executed'))
        return res

    def unlink(self):
        for r in self:
            productivity_ids = self.env['mrp.workcenter.productivity'].search([('step_id', '=', r.id)])
            if productivity_ids:
                raise ValidationError(_('Warning! {} of {} ({}) has tracking inputs'.format(r.product_id.complete_name,
                                                                                            r.workorder_id.product_wo.complete_name,
                                                                                            r.production_id.name)))
        super(LbmWorkOrderStep, self).unlink()

    def _compute_quality_count(self):
        for _id in self:
            _id.quality_count = self.env['quality.alert'].search_count([('product_id', '=', _id.product_id.id),
                                                                        ('stage_id.name', '!=', 'Solved')])

    @api.constrains('stage_id')
    def _check_stage(self):
        stages = self.get_stages_by_name()
        for _id in self:
            if not _id.wkcenter and _id.stage_id.id in [stages['working'], stages['blocked'], stages['finished']]:
                raise ValidationError(_('A Workcenter is required to move the step to: working, blocked or finished'))

    @api.depends('tracking_ratio', 'workorder_id.tracking_duration_expected')
    def _compute_duration_expected(self):
        for _id in self:
            _id.duration_expected = (_id.tracking_ratio * _id.workorder_id.tracking_duration_expected)/60

    @api.depends('tracking_ids.duration')
    def _compute_accum_duration(self):
        for _id in self:
            _id.accum_time = sum(_id.tracking_ids.filtered(lambda r: r.tracking_origin == 'step').mapped('duration'))/60

    @api.depends('tracking_ids', 'product_qty', 'tracking_ratio')
    def _compute_percent_complete(self):
        for r in self:
            tracking_qty = sum(r.tracking_ids.filtered(lambda y: y.tracking_origin == 'step').mapped('qty_progress'))
            r.percent_complete = tracking_qty / r.product_qty * 100 if r.product_qty else 0
            wo_complete = r.percent_complete * r.tracking_ratio
            r.percent_wo_complete = wo_complete if wo_complete <= 100 else r.tracking_ratio * 100
            wo_complete = sum(r.tracking_ids.mapped('wo_qty_progress'))
            r.full_percent_wo_complete = wo_complete if wo_complete <= 100 else r.tracking_ratio * 100

    @api.depends('tracking_ids', 'product_qty', 'workorder_id', 'tracking_ratio')
    def _compute_qty_progress(self):
        for r in self:
            r.qty_progress = sum(r.tracking_ids.mapped('qty_progress'))
            qty_progress = sum(r.tracking_ids.mapped('wo_qty_progress'))
            wo_progress = r.tracking_ratio * r.workorder_id.qty_production
            r.available_wo_qty_progress = wo_progress - qty_progress

    @api.depends('available_wo_qty_progress')
    def _compute_do_tracking(self):
        for r in self:
            r.do_tracking = True if r.available_wo_qty_progress > 0 else False

    @api.depends('timetracking_ids')
    def _compute_has_timetracking(self):
        for r in self:
            r.has_timetracking = True if len(r.timetracking_ids) >= 1 else False

    @api.depends('tracking_ids')
    def _compute_has_tracking(self):
        for r in self:
            r.has_tracking = True if len(r.tracking_ids.filtered(lambda y: y.tracking_origin == 'step')) >= 1 else False

    def show_step_tracking_form(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_work_order_step_form_view')
        is_readonly = False
        contexto = {'is_readonly': is_readonly, 'form_kanban': False}
        return {
            'name': '{0}: {1} / {2}'.format(_('Time Tracking'), self.product_id.name_get()[0][1], self.location),
            'res_model': 'lbm.work.order.step',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'context': contexto,
            'target': 'current',
            'height': 'auto',
            'width': '100%',
        }

    def show_quality_alert(self):
        self.ensure_one()
        return {
            'name': '{0}'.format(_('Quality Alert')),
            'res_model': 'lbm.work.order.step',
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', self.env['quality.alert'].search([('product_id', '=', self.product_id.id),
                                                                      ('workcenter_id', '=',
                                                                       self.wkcenter.id)]).ids)],
            'target': 'current'
        }

    def _get_float_hour(self, date):
        minute_arr = str(float(date.minute) / 60).split('.')
        return float('{0}.{1}'.format(date.hour, minute_arr[1]))

    def validate_stage_js(self):
        list_step_stop = []
        ModelData = self.env['ir.model.data']
        stage_stop = ModelData.get_object('aci_estimation', 'aci_stop_stage')
        stage_stop_id = self.env['lbm.work.order.step'].search([('stage_id', '=', stage_stop.id)]).ids
        context = self._context
        if not context.get('context_selection'):
            for _id in stage_stop_id:
                if _id in self.ids:
                    list_step_stop.append(_id)

            self = self.with_context(context_selection=True)
        return list_step_stop

    def set_duration_value(self):
        return 'done'

    def button_detailed_form(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_work_order_step_form_view')
        is_readonly = False
        contexto = {'is_readonly': is_readonly, 'form_kanban': False}
        return {
            'name': '{0}: {1}'.format(_('Time Tracking'), self.product_id.complete_name),
            'res_model': 'lbm.work.order.step',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'context': contexto,
            'target': 'current',
            'height': 'auto',
            'width': '100%',
        }

    def button_quality_alert(self):
        view_form_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'quality_alert_view_form_tracking')
        view_id = self.env['ir.model.data'].get_object(
            'quality_control', 'quality_alert_view_kanban')

        analytic_id = self._context.get('selected_analytic_id')
        default_analytic_id = analytic_id if analytic_id else None
        return {
            'name': _('Assign Quality Work Center'),
            'res_model': 'quality.alert',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'kanban'), (view_form_id.id, 'form')],
            'target': 'current',
            'context': {'default_workcenter_id': self.wkcenter.id,
                        'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
                        'default_activity_product_id': self.product_id.id,
                        'default_type': 'production',
                        'default_analytic_id': default_analytic_id},
            'domain': [('id', 'in', self.env['quality.alert'].search([('product_id', '=', self.product_id.id),
                                                                      ('workcenter_id', '=', self.wkcenter.id)]).ids)]
        }

    def get_stage_ids(self):
        ModelData = self.env['ir.model.data']
        stage_stop = ModelData.get_object(
            'aci_estimation', 'aci_stop_stage')
        stage_working = ModelData.get_object(
            'aci_estimation', 'aci_working_stage')
        stage_blocked = ModelData.get_object(
            'aci_estimation', 'aci_blocked_stage')
        stage_finished = ModelData.get_object(
            'aci_estimation', 'aci_finished_stage')
        stage_cancel = ModelData.get_object(
            'aci_estimation', 'aci_cancel_stage')

        stages = {};
        stages[str(stage_stop.id)] = 'stop'
        stages[str(stage_working.id)] = 'working'
        stages[str(stage_blocked.id)] = 'blocked'
        stages[str(stage_finished.id)] = 'finished'
        stages[str(stage_cancel.id)] = 'cancel'

        return stages

    def get_stages_by_name(self):
        return {v: int(k) for k, v in self.get_stage_ids().items()}

    def insert_all_times_from_wo(self, input_times):
        self.ensure_one()
        WkcenProd = self.env['mrp.workcenter.productivity']
        wkcenter = self.workorder_id.workcenter_id.id
        res_id = self.wkcenter.id
        # insert_times = []
        for input_time in input_times:
            WkcenProd.create({
                'step_id': self.id,
                'workcenter_id': wkcenter,
                'resource_id': res_id,
                'description': '[4]Time taken from Work Order, when change type to manage (Work order manage to step manage). ( ' + self.env.user.name + ' )',
                'loss_id': input_time['time_id'].loss_id.id,
                'date_start': input_time['time_id'].date_start,
                'date_end': input_time['time_id'].date_end,
                'user_id': self.env.user.id,
                'is_productivity': True
            })

    # ===

    def button_save_trackings(self):
        self.ensure_one()
        self.tracking_ids.filtered(lambda r: r.tracking_origin == 'step').adjust_tracking_dates()

    def show_tracking(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_work_order_step_tracks_form_view')
        is_readonly = self.manage_type != 'step'
        contexto = {'is_readonly': is_readonly, 'form_kanban': False}
        return {
            'name': '{0}: {1} / {2}'.format(_('Time Tracking'), self.product_id.name_get()[0][1], self.location),
            'res_model': 'lbm.work.order.step',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'context': contexto,
            'target': 'new'
        }

    def assign_workcenter(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'step_assign_single_wc_form_view')
        return {
            'name': _('Assign Work Center'),
            'res_model': 'lbm.work.order.step',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'new'
        }

    def null_button(self):
        return True

    def delete_tracking_btn(self):
        todo_stage_id = self.env['time.tracking.actions'].get_stage_id('ToDo')
        self.env['mrp.workcenter.productivity'].search([('step_id', '=', self.id)]).unlink()
        self.env['mrp.timetracking'].search([('step_id', '=', self.id)]).write({'stage_id': todo_stage_id})

    def show_tracking_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_tree_view')
        calendar_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_calendar_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activity',
            'views': [(view_id.id, 'tree'), (calendar_view_id.id, 'calendar')],
            'res_model': 'mrp.timetracking',
            'domain': [('id', 'in', self.timetracking_ids.ids)],
            'target': 'current'
        }

    def get_datetime_by_duration(self, calendar_id, date_start, duration):
        date_start = self.env['time.tracking.actions'].get_tz_datetime(date_start, self.env.user)
        date_end = None
        weekday = date_start.weekday()
        first_iteration = True
        while duration > 0:
            for att in calendar_id.attendance_ids.filtered(lambda r: r.dayofweek == str(weekday)):
                from_hour = int('{0:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
                from_minutes = int('{1:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
                to_hour = int('{0:02.0f}'.format(*divmod(att.hour_to * 60, 60)))
                to_minutes = int('{1:02.0f}'.format(*divmod(att.hour_to * 60, 60)))

                block_start = date_start.replace(hour=from_hour, minute=from_minutes, second=0)
                block_end = date_start.replace(hour=to_hour, minute=to_minutes, second=0)
                if block_end > date_start:
                    diff = block_end - date_start if first_iteration else block_end - block_start
                    block_duration = round(diff.total_seconds() / 60.0, 2)
                    if duration <= block_duration:
                        date_end = date_start + timedelta(minutes=duration) if first_iteration else block_start + timedelta(minutes=duration)
                        duration = 0
                    else:
                        duration = duration - block_duration
                    first_iteration = False
            weekday = weekday + 1 if weekday != 6 else 0
            date_start = date_start + timedelta(days=1)
        return self.env['time.tracking.actions'].remove_tz_datetime(date_end, self.env.user)