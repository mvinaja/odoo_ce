from odoo import models, fields, api, _


class MrpEstimationCalculator(models.TransientModel):
    _name = 'mrp.estimation.calculator'
    _description = 'Estimation Calculator'

    model_name = fields.Char()
    field_name = fields.Char()
    res_id = fields.Integer()
    float_result = fields.Float(default=1)
    int_result = fields.Integer(default=1)
    integer_number = fields.Boolean(default=True)
    decimal_number = fields.Boolean(default=False)
    mode = fields.Selection([('float', 'float'), ('integer', 'integer'), ('hour', 'hour')], default='float')

    def reload(self, view_id=None):
        context = self.env.context.copy()
        context.update({
            'default_model_name': self.model_name,
            'default_field_name': self.field_name,
            'default_res_id': self.res_id,
            'default_float_result': self.float_result,
            'default_int_result': self.int_result,
            'default_integer_number': self.integer_number,
            'default_decimal_number': self.decimal_number,
            'default_mode': self.mode,
            'return_action': context.get('return_action')
        })
        if not view_id:
            view_id = self.env['ir.model.data'].get_object(
                'aci_estimation', 'mrp_estimation_calculator_form_view')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'res_model': 'mrp.estimation.calculator',
            'name': 'Calculator//small',
            'target': 'new',
            'context': context
        }

    def return_result(self):
        context = self.env.context.copy()
        result = self.int_result if self.mode == 'integer' else self.float_result
        action = context.get('return_action')
        self.env[self.model_name].browse([self.res_id]).write({self.field_name: result})
        if action:
            return action

    def validate_result(self, result):
        partial_result = str(result).split('.')
        integer_number = False
        if len(partial_result) == 1:
            result = float('{}.00'.format(partial_result[0]))
        elif len(partial_result) == 0:
            result = 0.00
            integer_number = True
        return result, integer_number

    def update_result(self, expr):
        result = str(self.float_result).split('.') if self.mode == 'float' else self.int_result
        if expr == 'P':
            result = self.float_result
            self.decimal_number = True
        elif expr == 'C':
            self.integer_number = True
            self.decimal_number = False
            result = 0.00
        elif self.integer_number:
            result = expr
        elif not self.decimal_number:
            result = '{}{}.{}'.format(result[0], expr, result[1]) if self.mode == 'float' else '{}{}'.format(result, expr)
        elif self.decimal_number:
            decimal = int(result[1])
            if decimal == 0:
                result = float('{}.{}'.format(result[0], expr))
            elif decimal > 9:
                result = float('{}.{}'.format(result[0], expr))
            else:
                result = float('{}.{}{}'.format(result[0], decimal, expr))
        result, self.integer_number = self.validate_result(result)
        if self.mode == 'float':
            self.float_result = result
        else:
            self.int_result = result
        return self.reload()

    def number_1_btn(self, context=None):
        return self.update_result(1)

    def number_2_btn(self, context=None):
        return self.update_result(2)

    def number_3_btn(self, context=None):
        return self.update_result(3)

    def number_4_btn(self, context=None):
        return self.update_result(4)

    def number_5_btn(self, context=None):
        return self.update_result(5)

    def number_6_btn(self, context=None):
        return self.update_result(6)

    def number_7_btn(self, context=None):
        return self.update_result(7)

    def number_8_btn(self, context=None):
        return self.update_result(8)

    def number_9_btn(self, context=None):
        return self.update_result(9)

    def number_0_btn(self, context=None):
        return self.update_result(0)

    def expresion_point_btn(self, context=None):
        return self.update_result('P')

    def expresion_clear_btn(self, context=None):
        return self.update_result('C')

    def expresion_send_btn(self, context=None):
        return self.return_result()