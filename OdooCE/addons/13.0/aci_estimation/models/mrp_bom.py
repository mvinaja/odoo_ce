# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
from odoo.tools import float_round


class ReportBomStructure(models.AbstractModel):
    _inherit = 'report.mrp.report_bom_structure'
    _description = 'BOM Structure Report'

    def _get_operation_line(self, bom, qty, level):
        operations = []
        total = 0.0
        for operation in bom.operation_ids:
            costs_hour = operation.workcenter_id.costs_hour if operation.workcenter_id else 0
            name = operation.workcenter_id.name if operation.workcenter_id else ''
            duration_expected = operation.duration
            total = ((duration_expected / 60.0) * costs_hour)
            operations.append({
                'level': level or 0,
                'operation': operation,
                'name': operation.name + ' - ' + name,
                'duration_expected': duration_expected,
                'total': self.env.company.currency_id.round(total),
            })
        return operations

class MrpBomExplosion(models.Model):
    _inherit = 'mrp.bom.explosion'

    operation_burden = fields.Float()

    @api.model
    def init(self):
        self._cr.execute("""
        DROP MATERIALIZED VIEW IF EXISTS mrp_bom_explosion CASCADE;
            CREATE MATERIALIZED VIEW mrp_bom_explosion AS

            WITH RECURSIVE bom_explosion AS (
                SELECT
                    bom_id,
                    child_bom_id,
                    product_id,
                    position_key,
                    position_type,
                    product_qty,
                    type,
                    CASE
                        WHEN type <> 'workcenter' THEN 0
                        ELSE operation_duration / 60.0
                    END AS duration,
                    CASE
                        WHEN type <> 'workcenter' THEN 0
                        ELSE operation_duration / 60.0 * product_qty
                    END AS operation_burden
                FROM mrp_bom_line
                WHERE child_bom_id IS NULL OR implode IS TRUE

                UNION ALL

                SELECT
                    line.bom_id,
                    explosion.child_bom_id,
                    explosion.product_id,
                    explosion.position_key,
                    explosion.position_type,
                    CASE
                        WHEN line.implode THEN 0.0
                        WHEN explosion.type = 'overcost' THEN explosion.product_qty
                        ELSE line.product_qty * explosion.product_qty
                    END,
                    explosion.type,
                    CASE
                        WHEN line.implode THEN 0.0
                        ELSE line.product_qty * explosion.duration
                    END,
                    explosion.operation_burden
                FROM bom_explosion AS explosion
                JOIN mrp_bom_line AS line ON line.child_bom_id = explosion.bom_id
                WHERE line.is_bom = True
            )
            SELECT
                ROW_NUMBER() OVER(ORDER BY bom_id, type, product_id) AS id,
                bom_id,
                child_bom_id,
                product_id,
                position_key,
                position_type,
                type,
                SUM(product_qty) AS product_qty,
                SUM(duration) AS duration,
                SUM(operation_burden) AS operation_burden
            FROM bom_explosion
            GROUP BY bom_id, child_bom_id, product_id, position_key, position_type, type
        """)

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    type_analytic = fields.Boolean(string='Dynamic Analytic', default=False, store=True)
    type_qty = fields.Boolean(string='Allowed to exceed limit', default=False, store=True)

    #
    batch = fields.Selection([
        ('no', 'Once all products are processed'),
        ('yes', 'Once a minimum number of products is processed')], string='Next Operation',
        help="Set 'no' to schedule the next work order after the previous one. Set 'yes' to produce after the quantity set in 'Quantity To Process' has been produced.",
        default='no', required=True)
    batch_size = fields.Float('Quantity to Process', default=1.0)
    time_cycle_manual = fields.Float(
        'Manual Duration', default=60,
        help="Time in minutes. Is the time used in manual mode, or the first time supposed in real time when there are not any work orders yet.")

    @api.model
    def init(self):
        super(MrpBom, self).init()
        self._cr.execute(
            '''
                CREATE OR REPLACE FUNCTION
                estimate_explosion(id_company INTEGER, id_context INTEGER, id_bom INTEGER)
                RETURNS VOID AS $$
                BEGIN
                    PERFORM update_estimation(id_company, id_context, id_bom, 'explosion', estimation_lst)
                    FROM (
                        WITH explosion AS(
                            SELECT
                                bom.id AS bom_id,
                                expl.position_key,
                                COALESCE(SUM(
                                    CASE
                                        WHEN expl.child_bom_id IS NOT NULL THEN
                                            expl.product_qty * context.bom_amount
                                        WHEN expl.type = 'workcenter' THEN
                                            expl.operation_burden * property.value_float
                                        ELSE expl.product_qty * property.value_float
                                    END
                                ), 0) AS price
                            FROM mrp_bom AS bom
                            LEFT JOIN mrp_bom_explosion AS expl ON expl.bom_id = bom.id
                            LEFT JOIN mrp_bom_context AS context ON context.bom_id = expl.child_bom_id
                                AND context.company_id = id_company
                                AND context.context_bom = id_context
                            LEFT JOIN ir_property AS property ON property.name = 'context_price'
                                AND property.res_id = 'product.product,' || expl.product_id
                                AND property.company_id = id_company
                                AND property.context_bom = id_context
                            WHERE bom.id = id_bom
                            GROUP BY bom.id, expl.position_key
                        )
                        SELECT
                            ARRAY_AGG(
                                (position_key, price, 0)::estimation
                            ) FILTER(WHERE position_key IS NOT NULL) AS estimation_lst
                        FROM explosion
                        GROUP BY bom_id
                    ) t;
                END;
                $$ LANGUAGE plpgsql;
    ''')

    def update_operation_btn(self):
        form_view_id = self.env['ir.model.data'].get_object('aci_estimation', 'update_operation_bom_wizard_form_view')
        return {
            'name': _('Copy Operation Data'),
            'res_model': 'update.operation.bom.wizard',
            'type': 'ir.actions.act_window',
            'views': [(form_view_id.id, 'form')],
            'target': 'new',
            "context": {'default_source_bom_id': self.id,
                        'default_target_warehouse': self.context_bom.context_warehouse.id,
                        'default_target_context': self.context_bom.id}
        }

    def update_crew_btn(self):
        '''Import workcenter's crew members'''
        for _id in self:
            _id.workcenter_id = _id.product_id.workcenter_id.id
            _id.crew_member_ids.unlink()

            # Add new members
            member_cmds = []
            for member_id in _id.workcenter_id.crew_member_ids:
                member_cmds.append((0, False, {
                    'type': 'workcenter',
                    'product_id': member_id.product_id.id,
                    'effective_qty': member_id.quantity
                }))

            # Do it!
            _id.crew_member_ids = member_cmds


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    def name_get(self):
        result = []
        for _id in self:
            name = '{} Ver.{}'.format(_id.product_id.complete_name, _id.child_bom_version)
            if _id.child_bom_id.code:
                name = '{} Ref.{}'.format(name, _id.child_bom_id.code)
            result.append((_id.id, name))
        return result
