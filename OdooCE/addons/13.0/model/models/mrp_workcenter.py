# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    name = fields.Char(required=True)
    code = fields.Char(required=True, inverse='_update_alter_code')
    crew_capacity = fields.Integer(default=1)

    is_group = fields.Boolean('Is Group', default=False)
    costs_hour = fields.Float(
        'Cost Per Hour', compute='_compute_costs_hour', store=True)

    department_id = fields.Many2one(
        'hr.department', 'Department', inverse='_update_alter_department', ondelete='restrict')

    resource_type = fields.Selection([
        ('template', 'Template'),
        ('alternative', 'Alternative')
    ], default='template', required=True)
    template_id = fields.Many2one(
        'mrp.workcenter', 'Template Workcenter', ondelete='cascade')
    contract_id = fields.Many2one('hr.contract', ondelete='restrict')
    contract_department_id = fields.Many2one(related='contract_id.department_id', string='Contract Department')
    employee_id = fields.Many2one(related='contract_id.employee_id', string='Operator', store=True)
    employee_department_id = fields.Many2one(related='employee_id.department_id', string='Employee Department')

    alternative_qty = fields.Integer('Alternative', default=1)
    alternative_workcenter_ids = fields.Many2many(domain="[]")
    crew_member_ids = fields.One2many('mrp.workcenter.member', 'workcen_id')

    @api.model
    def create(self, vals):
        '''Create alternative workcenters'''
        #Todo
        if 'resource_type' not in vals.keys():
            vals['resource_type'] = 'template'
        mrp_workcen = super(MrpWorkcenter, self).create(vals)

        # Evaluate if workcenter is type of template
        if mrp_workcen.resource_type == 'template':
            alternative_cmds = []
            for indx in range(1, mrp_workcen.alternative_qty + 1, 1):
                default_vals = {
                    'name': '{}_{}'.format(mrp_workcen.name, indx),
                    'code': '{}_{}'.format(mrp_workcen.code, indx),
                    'sequence': indx,
                    'resource_calendar_id': mrp_workcen.resource_calendar_id.id,
                    'resource_type': 'alternative',
                    'alternative_qty': 0,
                    'department_id': mrp_workcen.department_id.id,
                    'template_id': mrp_workcen.id
                }
                alternative_cmds.append((0, False, default_vals))

            # Do it!
            mrp_workcen.write({'alternative_workcenter_ids': alternative_cmds})

        return mrp_workcen

    def write(self, vals):
        '''Update alternative workcenters when alternative quantity changes'''

        # Create / remove alternative workcenters
        if 'alternative_qty' in vals.keys():
            new_quantity = vals.get('alternative_qty')
            for _id in self.filtered(lambda r: r.resource_type == 'template'):
                max_sequence = len(_id.alternative_workcenter_ids)
                delta = new_quantity + 1 - max_sequence
                if delta > 0:
                    # Create new workcenters
                    alternative_cmds = []
                    for indx in range(1, delta, 1):
                        sequence = indx + max_sequence
                        alternative_cmds.append((0, False, {
                                'template_id': _id.id,
                                'name': '{}_{}'.format(_id.name, sequence),
                                'code': '{}_{}'.format(_id.code, sequence),
                                'sequence': sequence,
                                'resource_type': 'alternative',
                                'alternative_qty': 0,
                                'department_id': _id.department_id.id
                            }))
                    _id.write({'alternative_workcenter_ids': alternative_cmds})
                else:
                    # Delete removed workcenters
                    removed_ids = _id.alternative_workcenter_ids.filtered(lambda r: r.sequence > new_quantity)
                    removed_ids.unlink()

        # Name fix
        if 'name' in vals.keys():
            name = vals.get('name')
            for _alt in self.filtered(lambda r: r.resource_type == 'template').alternative_workcenter_ids:
                _alt.name = '{}_{}'.format(name, _alt.sequence)
        return super(MrpWorkcenter, self).write(vals)

    def name_get(self):
        res = []
        for _id in self:
            if _id.resource_type == 'template':
                # Workcenter template
                res.append((_id.id, _id.name))
            # elif _id.employee_id.name:
            #     # From employee name
            #     res.append((_id.id, _id.employee_id.name))
            else:
                # From alternative code
                res.append((_id.id, _id.code))

        return res

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = ['|', '|', ('name', operator, name), ('code', operator, name), ('employee_id.name', operator, name)]

        workcenter_ids = self.search(domain + args, limit=limit)
        return workcenter_ids.name_get()

    def _update_alter_code(self):
        '''Update template code to alternative workcenters'''
        for _id in self:
            for alternative_id in _id.mapped('alternative_workcenter_ids'):
                alternative_id.code = '{}_{}'.format(_id.code, alternative_id.sequence)

    def _update_alter_department(self):
        '''Update template department to alternative workcenters'''
        for _id in self:
            alternative_ids = _id.mapped('alternative_workcenter_ids')
            for alternative in alternative_ids:
                if alternative.department_id.id != _id.department_id.id:
                # if not self._valid_department(alternative.department_id.id, _id.department_id.id):
                    alternative.write({'department_id': _id.department_id.id, 'employee_id': False})

    def _valid_department(self, department_id, parent_department_id):
        current_department_id = self.env['hr.department'].search([('id', '=', department_id)])
        while current_department_id:
            if current_department_id.id == parent_department_id:
                return True
            current_department_id = self.env['hr.department'].search([('id', '=', current_department_id.parent_id.id)])
        return False

    @api.constrains('employee_id')
    def check_crew_members(self):
        for _id in self.filtered(lambda r: r.employee_id):
            if not _id.employee_id.contract_ids:
                raise exceptions.ValidationError(
                    _('Employee {} does not have a contract.'.format(_id.employee_id.name)))

    @api.depends('crew_member_ids.member_cost')
    def _compute_costs_hour(self):
        for _id in self:
            _id.costs_hour = sum(_id.crew_member_ids.mapped('member_cost'))

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        '''Evaluate if employee already have a workcenter'''
        if self.employee_id:
            workcen_ids = self.search([('employee_id', '=', self.employee_id.id)])
            # if workcen_ids:
            #     message = 'Employee "{}" is being used on workcenter alternative(s) {}'\
            #             .format(self.employee_id.name, ','.join(workcen_ids.mapped('name')))
            #     return {'warning': {
            #         'title': _('Warning'),
            #         'message': _(message)
            #     }}

    @api.onchange('department_id')
    def onchange_department(self):
        if not self.template_id:
            show_message = False
            alt = []
            for alternative in self.alternative_workcenter_ids:
                if not self._valid_department(alternative.department_id.id, self.department_id.id) and alternative.employee_id:
                    show_message = True
                    alt.append(alternative.name)
            if show_message:
                message = 'The parent department {}, will delete the following Alternative Operator(s) : \n"{}"' \
                          '\n DISCARD the edition if you want to keep their operators.' \
                    .format(self.department_id.name, ', '.join(alt))
                return {'warning': {
                    'title': _('Warning'),
                    'message': _(message)
                }}

    def add_crew_member_btn(self):
        self.ensure_one()

        view_id = self.env.ref('aci_product.mrp_workcenter_member_tree_view')
        former_products = self.crew_member_ids.mapped('product_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add Crew Members'),
            'views': [(view_id.id, 'tree')],
            'res_model': 'product.product',
            'target': 'current',
            'domain': [
                ('id', 'not in', former_products.ids),
                ('product_tmpl_id.categ_type', '=', 'labor')],
            'context': {'default_workcen_id': self.id}
        }

    def show_alternative_btn(self):
        self.ensure_one()
        view_id = self.env.ref('aci_product.mrp_workcenter_alternative_tree_view')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alternative(s)'),
            'views': [(view_id.id, 'tree')],
            'res_model': 'mrp.workcenter',
            'target': 'current',
            'domain': [('id', 'in', self.alternative_workcenter_ids.ids)]
        }

class MrpWorkcenterMember(models.Model):
    _name = 'mrp.workcenter.member'
    _description = 'Work Center Member'
    _rec_name = 'product_id'

    quantity = fields.Integer('Quantity', default=1)

    product_price = fields.Float('Unit Price', related='product_id.fasar_base', readonly=True)
    product_cost = fields.Float('Dir. Cost', compute='_compute_cost')

    fasar_price = fields.Float('Fsr. Price', related='product_id.context_price', readonly=True)
    fasar_cost = fields.Float('Fsr. Cost', compute='_compute_cost')

    member_cost = fields.Float('Member Cost', compute='_compute_cost')

    position_key = fields.Many2one(related='product_id.position_key', store=True)
    product_id = fields.Many2one('product.product', 'Member', required=True)
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', readonly=True, store=True)
    workcen_id = fields.Many2one('mrp.workcenter', ondelete='cascade')

    @api.depends('quantity')
    def _compute_cost(self):
        for _id in self:
            _id.member_cost = _id.product_price * _id.quantity
            _id.product_cost = _id.product_price * _id.quantity
            _id.fasar_cost = _id.fasar_price * _id.quantity


class MrpResources(models.Model):
    _inherit = 'resource.resource'

    resource_type = fields.Selection(selection_add=[
        ('template', 'Template'),
        ('alternative', 'Alternative')
    ], ondelete={'template': 'set default', 'alternative': 'set default'})
