# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _
from odoo.exceptions import ValidationError as Error


class AddWorkorderStepWizard(models.TransientModel):
    _name = 'add.workorder.step.wizard'
    _description = 'add.workorder.step.wizard'

    product_qty = fields.Float('Quantity', default=1.0)
    rate = fields.Float('Rate', default=1.0)
    type = fields.Selection([
        ('material', 'As Components'),
        ('workstep', 'As Worksteps')
    ], string='As', default='material')
    origin = fields.Selection([
        ('bom', 'Bill Of Materials'),
        ('component', 'Components'),
        ('product', 'Raw Materials')
    ], string='Append', default='bom')

    components_bom = fields.Many2one('mrp.bom', 'Components From')
    source_boms = fields.Many2many(
        'mrp.bom', 'add_workorder_step__source_boms', string='Bill Of Materials')
    source_lines = fields.Many2many(
        'mrp.bom.line', 'add_workorder_step__source_lines', string='Components')
    source_products = fields.Many2many(
        'product.product', 'add_workorder_step__source_products', string='Products')

    context_warehouse = fields.Many2one('stock.warehouse', string='Warehouse')
    context_bom = fields.Many2one('mrp.bom')

    target_workorder = fields.Many2one('mrp.workorder', string='To Workorder')
    crew_amount = fields.Float(
        'Crew Cost', related='target_workorder.operation_id.crew_amount', readonly=True)
    operation_amount = fields.Float('Pay Amount', related='target_workorder.direct_cost', readonly=True)
    operation_extra = fields.Float('Extra Amount', related='target_workorder.operation_extra', readonly=True)
    operation_labor = fields.Float(related='target_workorder.labor_cost', readonly=True)
    workstep_extra = fields.Float(compute='_compute_workstep_extra')
    workstep_ids = fields.One2many('add.workorder.step.line', 'wizard_id')

    @api.model
    def default_get(self, fields):
        res = super(AddWorkorderStepWizard, self).default_get(fields)
        res['context_warehouse'] = self.env.context.get('context_warehouse')
        res['target_workorder'] = self.env.context.get('active_id')
        return res

    @api.onchange('context_warehouse')
    def onchange_context_warehouse(self):
        self.components_bom = False

    @api.onchange('workstep_ids')
    def onchange_workstep_ids(self):
        bom_ids = self.workstep_ids.bom_id
        parents = bom_ids.parent_bom_ids.filtered(lambda r: r.bom_type == 'budget')
        return {'domain': {'context_bom': [('id', 'in', parents.ids)]}}

    @api.onchange('source_boms', 'source_lines', 'source_products')
    def onchange_source_products(self):
        existing_products = self.workstep_ids.product_id
        # if self.type == 'material':
        #     existing_products += self.target_workorder.component_ids.product_id
        # else:
        #     existing_products += self.target_workorder.step_ids.product_id

        values = {}
        if self.origin == 'bom':
            bom_ids = self.source_boms.filtered(lambda r: r.product_id not in existing_products)
            for bom_id in bom_ids:
                values[bom_id.product_id.id] = {'type': 'bom', 'bom_id': bom_id.id.origin}

        elif self.origin == 'component':
            line_ids = self.source_lines.filtered(lambda r: r.product_id not in existing_products)
            for line_id in line_ids:
                values[line_id.product_id.id] = {'type': 'component', 'line_id': line_id.id.origin}

        elif self.origin == 'product':
            Product = self.env['product.product']
            for product_id in self.source_products.filtered(lambda r: r.id.origin not in existing_products.ids):
                values[product_id.id.origin] = {'type': 'product'}

        worksteps = []
        for id_product, values in values.items():
            values.update({
                'product_id': id_product,
                'rate': self.rate,
                'product_qty': self.product_qty,
            })
            worksteps.append((0, False, values))
        self.workstep_ids = worksteps
        self.source_boms = False
        self.source_lines = False
        self.source_products = False

    def _compute_workstep_extra(self):
        for _id in self:
            extra_value = 0
            for workstep in _id.step_ids.filtered(lambda r: r.add_value):
                extra_value += workstep.duration * workstep.value_factor
            if extra_value:
                _id.workstep_extra = _id.target_workorder.operation_extra / extra_value
            else:
                _id.workstep_extra = 0

    def add_workstep_btn(self):
        '''Add components'''
        if self.type == 'material':
            Component = self.env['mrp.workorder.component']
            product_ids = self.target_workorder.component_ids.product_id
            for workstep in self.workstep_ids.filtered(lambda r: r.product_id not in product_ids):
                component_id = Component.create({
                    'workorder_id': self.target_workorder.id,
                    'product_id': workstep.product_id.id,
                    'wbs_key': workstep.wbs_key,
                    'party_id': workstep.party_id.id,
                    'categ_id': workstep.categ_id.id,
                    'product_qty': workstep.product_qty,
                    'effective_qty': workstep.product_qty,
                    'unit_price': workstep.unit_price,
                    'component_price': workstep.component_price,
                    'type': workstep.type,
                    'origin': 'manufacturing',
                    'bom_id': workstep.bom_id.id,
                    'line_id': workstep.line_id.id
                })
                component_id.explode()

        else:
            workstep_cmds = []
            product_ids = self.target_workorder.step_ids.product_id
            for workstep in self.workstep_ids.filtered(lambda r: r.product_id not in product_ids):
                workstep_cmds.append((0, False, {
                    'manual': True,
                    'product_id': workstep.product_id.id,
                    'wkcenter': self.target_workorder.resource_id.id,
                    'net_cost': 0,
                    'extra_cost': 0,
                    'ratio': 0,
                    'rate': workstep.rate,
                    'workstep_id': workstep.bom_id.id,
                    'rate_uom': workstep.rate_uom.id,
                    'time_uom': workstep.time_uom.id,
                    'product_qty': workstep.product_qty
                }))
            self.target_workorder.step_ids = workstep_cmds


class AddWorkorderStepLine(models.TransientModel):
    _name = 'add.workorder.step.line'
    _description = 'add.workorder.step.line'

    @api.model
    def _default_time_uom(self):
        return self.env.ref('uom.product_uom_hour').id

    wizard_id = fields.Many2one('add.workorder.step.wizard')
    sequence = fields.Integer()
    rate = fields.Float('Rate', default=0.0)
    rate_uom = fields.Many2one(related='product_id.uom_id', readonly=True)
    time_uom = fields.Many2one('uom.uom', default=_default_time_uom)
    duration = fields.Float('Duration', compute='_compute_duration')

    context_bom = fields.Many2one(related='wizard_id.context_bom', readonly=True)
    type = fields.Selection([
        ('bom', 'Bill Of Materials'),
        ('component', 'Components'),
        ('product', 'Raw Materials')
    ], default='bom')
    product_id = fields.Many2one('product.product', required=True, ondelete='cascade')
    bom_id = fields.Many2one('mrp.bom')
    line_id = fields.Many2one('mrp.bom.line')
    product_qty = fields.Float('Quantity')
    add_value = fields.Boolean(
        'E. Value', related='product_id.add_value', readonly=True)
    value_factor = fields.Float('E. Factor', default=1.0)
    categ_id = fields.Many2one(related='product_id.categ_id', readonly=True)
    party_id = fields.Many2one(related='product_id.party_id', readonly=True)
    wbs_key = fields.Char()

    unit_price = fields.Float('Unit Price', compute='_compute_component_price')
    component_price = fields.Float('Component Price', compute='_compute_component_price')

    unit_labor = fields.Float('U. C. L.', compute='_compute_workstep_unit')
    unit_extra = fields.Float('U. E.', compute='_compute_workstep_unit')
    labor_cost = fields.Float('C. L.', compute='_compute_workstep_cost')
    extra_cost = fields.Float('I. E.', compute='_compute_workstep_cost')
    pay_amount = fields.Float('P. A.', compute='_compute_workstep_cost')
    crew_amount = fields.Float('Crew Cost', related='wizard_id.crew_amount', readonly=True)

    @api.depends('rate', 'product_qty')
    def _compute_duration(self):
        '''Compute workstep duration'''
        for _id in self:
            if _id.rate:
                _id.duration = _id.product_qty / _id.rate
            else:
                _id.duration = 0.0

    @api.depends('context_bom', 'bom_id', 'line_id', 'product_id', 'product_qty')
    def _compute_component_price(self):
        for _id in self:
            if _id.type == 'bom':
                bom_id = _id.bom_id.with_context(default_context_bom=_id.context_bom.id)
                unit_price = bom_id.context_price
            elif _id.type == 'component':
                line_id = _id.line_id.with_context(default_context_bom=_id.context_bom.id)
                unit_price = _id.line_id.unit_price
            else:
                unit_price = _id.product_id.standard_price
            _id.unit_price = unit_price
            _id.component_price = unit_price * _id.product_qty

    @api.depends('rate', 'product_qty')
    def _compute_workstep_unit(self):
        '''Workstep's direct and fasar cost'''
        for _id in self:
            _id.unit_labor = _id.rate and _id.crew_amount / _id.rate or 0
            if _id.add_value:
                _id.unit_extra = (_id.wizard_id.workstep_extra * _id.duration * _id.value_factor) / _id.product_qty
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
            operation_labor = _id.wizard_id.operation_labor
            pay_amount = operation_labor and _id.labor_cost / operation_labor or 0
            _id.pay_amount = _id.wizard_id.operation_amount * pay_amount


class CopyWorkorderStepWizard(models.TransientModel):
    _name = 'copy.workorder.step.wizard'
    _description = 'copy.workorder.step.wizard'

    action = fields.Selection([
        ('component', 'Duplicate components'),
        ('new', 'Duplicate manual steps'),
        ('copy', 'Copy steps params')
    ], default='component', required=True)
    source_workorder = fields.Many2one('mrp.workorder', string='From Workorder')
    target_workorders = fields.Many2many(
        'mrp.workorder', 'copy_workorder_step__target_workorders', string='To Workorders')

    def perform_action(self):
        for workorder_id in self.target_workorders:
            if self.action == 'component':
                products = workorder_id.component_ids.product_id
                components = self.source_workorder.component_ids
                for line in components.filtered(lambda r: r.product_id not in products):
                    new_id = line.copy({'workorder_id': workorder_id.id})
                    new_id.explode()
            elif self.action == 'new':
                products = workorder_id.step_ids.product_id
                steps = self.source_workorder.step_ids.filtered('manual')
                for step in steps.filtered(lambda r: r.product_id not in products):
                    step.copy({'workorder_id': workorder_id.id})
            else:
                for source_step in self.source_workorder.step_ids:
                    target_step = workorder_id.step_ids.filtered(lambda r: r.product_id == source_step.product_id)
                    target_step.write({
                        'rate': source_step.rate,
                        'product_qty': source_step.product_qty,
                        })
