from odoo import http
from odoo.http import content_disposition, request
from odoo.exceptions import UserError
from odoo.addons.web_studio.controllers import export

import io
import xlsxwriter
import datetime


class MrpRoutingController(http.Controller):

    @http.route('/aci_mrp_plm/compare_bom', type='http', auth='user')
    def download_excel(self, src_ctx=None, src_bom=None, tgt_ctx=None, tgt_bom=None, rep_type=None, **kw):
        io_buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(io_buffer, {'in_memory': True})
        worksheet = workbook.add_worksheet()
        bold = workbook.add_format({'bold': 1})

        Bom = request.env['mrp.bom']
        source_bom = Bom.browse(int(src_bom))
        target_bom = Bom.browse(int(tgt_bom))
        src_context = Bom.browse(int(src_ctx))
        tgt_context = Bom.browse(int(tgt_ctx))

        # Print Titles
        worksheet.write('G1', '(A) Ctx', bold)
        worksheet.write('G2', '(B) Ctx', bold)
        worksheet.write('H1', '{}'.format(src_context.name))
        worksheet.write('H2', '{}'.format(tgt_context.name))

        titles = [
                  'ID',
                  'Category',
                  'Type',
                  'Budg. Pos.',
                  'Product',
                  'UoM',
                  '(A) {}'.format(source_bom.name),
                  '(B) {}'.format(target_bom.name),
                  'Coincident',
                  'A QTY',
                  'B QTY',
                  'A Price',
                  'B Price',
                  'A Cost',
                  'B Cost',
                  'A - B Cost']

        if rep_type == 'step':
            titles.insert(9, 'A U.C.L')
            titles.insert(10, 'B U.C.L')
            titles.insert(11, 'A U.B')
            titles.insert(12, 'B U.B')
            titles.insert(13, 'A P.A')
            titles.insert(14, 'B P.A')
            titles.insert(15, 'A C.L')
            titles.insert(16, 'B C.L')

        if rep_type == 'component':
            titles.insert(len(titles), 'A Pay Amnt')
            titles.insert(len(titles), 'B Pay Amnt')
            titles.insert(len(titles), 'A Extra Amnt')
            titles.insert(len(titles), 'B Extra Amnt')
        elif rep_type == 'step' and source_bom.bom_type == 'model':
            titles.insert(4, 'Workorder')
            worksheet.set_column(5, 5, 30)

        for code in range(ord('A'), ord('A') + len(titles)):
            worksheet.write('{}4'.format(chr(code)), titles[code - ord('A')], bold)

        worksheet.set_column(0, 0, 5)
        worksheet.set_column(1, 1, 20)
        worksheet.set_column(4, 4, 30)

        # Fill table
        if rep_type == 'explosion':
            query_result = self.compare_bom_explosion(src_ctx, source_bom, tgt_ctx, target_bom)
        elif rep_type == 'component':
            query_result = self.compare_bom_material(src_ctx, source_bom, tgt_ctx, target_bom, 'material')
        elif rep_type == 'step':
            query_result = self.compare_bom_material(src_ctx, source_bom, tgt_ctx, target_bom, 'workstep')
        else:
            query_result = None

        row_indx = 4
        if query_result:
            for row in query_result:
                col_indx = 0
                for value in row.values():
                    worksheet.write(row_indx, col_indx, value)
                    col_indx += 1
                row_indx += 1
        workbook.close()

        time_stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M")
        file_name = 'Compare-BoM_{}_{}.xlsx'.format(rep_type, time_stamp)

        response = request.make_response(None, [
            ('Content-Type', 'application/octet-stream; charset=binary'),
            ('Content-Disposition', content_disposition(file_name))
        ])

        io_buffer.seek(0)
        response.stream.write(io_buffer.read())
        io_buffer.close()

        response.direct_passthrough = True
        return response

    def compare_bom_explosion(self, src_ctx, source_bom, tgt_ctx, target_bom):
        request.env.cr.execute('''

                        WITH property AS (
                        SELECT
                            company_id, context_bom, res_id, value_float as context_price
                        FROM ir_property
                        WHERE name IN ('context_price', 'fasar_factor')
                        GROUP BY res_id, company_id, context_bom, value_float
                    ), explosion AS (
                        SELECT
                            expl.bom_id,
                            bom.name AS bom_name,
                            categ.complete_name AS category,
                            expl.product_id,
                            variant.complete_name AS product_name,
                            uom.name AS uom_name,
                            variant.neodata_id,
                            expl.type,
                            expl.product_qty,
                            budgetary.name as position_key
                        FROM mrp_bom_explosion AS expl
                        JOIN mrp_bom AS bom ON bom.id = expl.bom_id
                        JOIN product_product AS variant ON variant.id = expl.product_id
                        JOIN product_template AS template ON template.id = variant.product_tmpl_id
                        JOIN uom_uom AS uom ON uom.id = template.uom_id
                        JOIN product_category AS categ ON categ.id = template.categ_id
                        JOIN account_budget_post AS budgetary ON budgetary.id = categ.position_key
                        WHERE expl.type <> 'crew'
                    ), source AS (
                        SELECT
                            expl.*,
                            COALESCE(property.context_price, 0.0) AS price
                        FROM explosion AS expl
                        LEFT JOIN property
                            ON property.res_id = 'product.product,' || expl.product_id
                            AND property.context_bom = %s
                        WHERE bom_id = %s
                    ), target AS (
                        SELECT
                            expl.*,
                            COALESCE(property.context_price, 0.0) AS price
                        FROM explosion AS expl
                        LEFT JOIN property
                            ON property.res_id = 'product.product,' || expl.product_id
                            AND property.context_bom = %s
                        WHERE bom_id = %s
                    )
                    SELECT
			            ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS id,
                        COALESCE(a.category, b.category) AS category,
                        COALESCE(a.type, b.type) AS type,
                        COALESCE(a.position_key, b.position_key) AS position_key,
                        COALESCE(a.product_name, b.product_name) AS product_name,
                        COALESCE(a.uom_name, b.uom_name) AS uom_name,
                        CASE WHEN a.bom_id IS NOT NULL
                            THEN 'X'
                        END AS belongs_a,
                        CASE WHEN b.bom_id IS NOT NULL
                            THEN 'X'
                        END AS belongs_b,
                        CASE WHEN a.bom_id IS NOT NULL and b.bom_id is NOT NULL
                            THEN 'X'
                        END AS coincident,
                        ROUND(a.product_qty::NUMERIC, 2) AS a_qty,
                        ROUND(b.product_qty::NUMERIC, 2) AS b_qty,
                        ROUND(a.price::NUMERIC, 2) AS a_price,
                        ROUND(b.price::NUMERIC, 2) AS b_price,
                        ROUND((a.product_qty * a.price)::NUMERIC, 2) as a_cost,
                        ROUND((b.product_qty * b.price)::NUMERIC, 2) as b_cost,
                        ROUND((a.product_qty * a.price)::NUMERIC, 2) - ROUND((b.product_qty * b.price)::NUMERIC, 2) as diff
                    FROM source AS a
                    FULL JOIN target AS b ON a.product_id = b.product_id
                    ORDER BY id

                    ''', ([src_ctx, source_bom.id, tgt_ctx, target_bom.id]))

        return request.env.cr.dictfetchall()

    def compare_bom_material(self, src_ctx, source_bom, tgt_ctx, target_bom, type):
        if type == 'workstep':
            product_name = 'COALESCE(a.product_name, b.product_name) AS product_name,'
            product_join = 'FULL JOIN target AS b ON a.product_id = b.product_id ' \
                           'AND a.bom_template_name = b.bom_template_name'
            amount_join = ''
            workstep_cost = ''',
                            CASE 
                            WHEN expl.rate > 0 THEN COALESCE(bom_cost.crew_amount, 0.0) / expl.rate
                            WHEN expl.rate <= 0 THEN 0
                                        END AS unit_labor,
                                        CASE 
                            WHEN expl.rate > 0 THEN COALESCE(bom_cost.crew_burden, 0.0) / expl.rate
                            WHEN expl.rate <= 0 THEN 0
                                        END AS unit_fasar,
                                        CASE 
                            WHEN COALESCE(bom_cost.operation_labor, 0.0) <= 0 THEN 0
                            WHEN expl.rate <= 0 THEN 0
                            ELSE COALESCE(bom_cost.crew_amount, 0.0) / expl.rate * expl.product_qty / bom_cost.operation_labor *  bom_cost.operation_amount
                                        END AS pay_amount,
                                        CASE 
                            WHEN expl.rate <= 0 THEN 0
                            ELSE COALESCE(bom_cost.crew_amount, 0.0) / expl.rate * expl.product_qty
                                        END AS labor_cost'''
            workstep_column = ''' 
                        ROUND(a.unit_labor::NUMERIC, 2) AS a_unit_labor,
                        ROUND(b.unit_labor::NUMERIC, 2) AS b_unit_labor,
                        ROUND(a.unit_fasar::NUMERIC, 2) AS a_unit_fasar,
                        ROUND(b.unit_fasar::NUMERIC, 2) AS b_unit_fasar,
                        ROUND(a.pay_amount::NUMERIC, 2) AS a_pay_amount,
                        ROUND(b.pay_amount::NUMERIC, 2) AS b_pay_amount,
                        ROUND(a.labor_cost::NUMERIC, 2) AS a_labor_cost,
                        ROUND(b.labor_cost::NUMERIC, 2) AS b_labor_cost,'''
        else:
            product_name = 'COALESCE(a.template_name, b.template_name) AS product_name,'
            product_join = 'FULL JOIN target AS b ON a.product_tmpl_id = b.product_tmpl_id'
            amount_join = ''',ROUND(a.operation_amount::NUMERIC, 2) as a_operation_amount,
                        ROUND(b.operation_amount::NUMERIC, 2) as b_operation_amount,
                        ROUND(a.operation_extra::NUMERIC, 2) as a_operation_extra,
                        ROUND(b.operation_extra::NUMERIC, 2) as b_operation_extra'''
            workstep_cost = ''
            workstep_column = ''

        if source_bom.bom_type == 'model' and type == 'workstep':
            src_bom_ids = [str(_id) for _id in source_bom.material_ids.mapped('child_bom_id').ids]
            tgt_bom_ids = [str(_id) for _id in target_bom.material_ids.mapped('child_bom_id').ids]
            src_bom_ids = '({})'.format(','.join(src_bom_ids))
            tgt_bom_ids = '({})'.format(','.join(tgt_bom_ids))
            child_bom_name = 'COALESCE(a.bom_template_name, b.bom_template_name) AS bom_template_name,'
        else:
            src_bom_ids = '({})'.format(source_bom.id)
            tgt_bom_ids = '({})'.format(target_bom.id)
            child_bom_name = ''

        request.env.cr.execute('''
                    WITH explosion AS (
                        SELECT
                            expl.bom_id,
                            expl.child_bom_id,
                            bom.name AS bom_name,
                            categ.complete_name AS category,
                            expl.product_id,
                            expl.product_tmpl_id,
                            bom_template.name AS bom_template_name,
                            variant.complete_name AS product_name,
                            template.name AS template_name,
                            uom.name AS uom_name,
                            variant.neodata_id,
                            expl.product_qty,
                            expl.type,
                            budgetary.name as position_key,
                            warehouse.company_id,
                            expl.rate
                        FROM mrp_bom_line AS expl
                        JOIN mrp_bom AS bom ON bom.id = expl.bom_id
                        JOIN product_product AS bom_variant ON bom_variant.id = bom.product_id
                        JOIN product_template AS bom_template ON bom_template.id = bom_variant.product_tmpl_id
                        JOIN product_product AS variant ON variant.id = expl.product_id
                        JOIN product_template AS template ON template.id = variant.product_tmpl_id
                        JOIN uom_uom AS uom ON uom.id = template.uom_id
                        JOIN product_category AS categ ON categ.id = template.categ_id
                        JOIN stock_warehouse AS warehouse ON warehouse.id = bom.context_warehouse
                        JOIN account_budget_post AS budgetary ON budgetary.id = categ.position_key
                        WHERE expl.type = %s
                    ), source AS (
                        SELECT
                            expl.*,
                            bom_ctx.id as bom_ctx,
                            COALESCE(bom_ctx.bom_amount, 0.0) AS price,
                            COALESCE(bom_ctx.operation_amount, 0.0) AS operation_amount,
                            COALESCE(bom_ctx.operation_extra, 0.0) AS operation_extra
                            {0}
                        FROM explosion AS expl
                        LEFT JOIN mrp_bom_context AS bom_ctx ON bom_ctx.company_id = expl.company_id AND
                            bom_ctx.context_bom = %s AND bom_ctx.bom_id = expl.child_bom_id
                        LEFT JOIN mrp_bom_context AS bom_cost ON bom_cost.company_id = expl.company_id AND
                            bom_cost.context_bom = %s AND bom_cost.bom_id = expl.bom_id
                        WHERE expl.bom_id in {1}
                    ), target AS (
                        SELECT
                            expl.*,
                            bom_ctx.id as bom_ctx,
                            COALESCE(bom_ctx.bom_amount, 0.0) AS price,
                            COALESCE(bom_ctx.operation_amount, 0.0) AS operation_amount,
                            COALESCE(bom_ctx.operation_extra, 0.0) AS operation_extra
                            {0}
                        FROM explosion AS expl
                        LEFT JOIN mrp_bom_context AS bom_ctx ON bom_ctx.company_id = expl.company_id AND
                            bom_ctx.context_bom = %s AND bom_ctx.bom_id = expl.child_bom_id
                        LEFT JOIN mrp_bom_context AS bom_cost ON bom_cost.company_id = expl.company_id AND
                            bom_cost.context_bom = %s AND bom_cost.bom_id = expl.bom_id
                        WHERE expl.bom_id in {2}
                    )
                    SELECT
                        ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) AS id,
                        COALESCE(a.category, b.category) AS category,
                        COALESCE(a.type, b.type) AS type,
                        COALESCE(a.position_key, b.position_key) AS position_key,
                        {3}
                        {4}
                        COALESCE(a.uom_name, b.uom_name) AS uom_name,
                        CASE WHEN a.bom_id IS NOT NULL
                            THEN 'X'
                        END AS belongs_a,
                        CASE WHEN b.bom_id IS NOT NULL
                            THEN 'X'
                        END AS belongs_b,
                        CASE WHEN a.bom_id IS NOT NULL and b.bom_id is NOT NULL
                            THEN 'X'
                        END AS coincident,
                        {5}
                        ROUND(a.product_qty::NUMERIC, 2) AS a_qty,
                        ROUND(b.product_qty::NUMERIC, 2) AS b_qty,
                        ROUND(a.price::NUMERIC, 2) AS a_price,
                        ROUND(b.price::NUMERIC, 2) AS b_price,
                        ROUND((a.product_qty * a.price)::NUMERIC, 2) as a_product_price,
                        ROUND((b.product_qty * b.price)::NUMERIC, 2) as b_product_price,
                        ROUND((a.product_qty * a.price)::NUMERIC, 2) - ROUND((b.product_qty * b.price)::NUMERIC, 2) as diff
                        {6}
                    FROM source AS a
                    {7}
                    ORDER BY id

                    '''.format(workstep_cost, src_bom_ids, tgt_bom_ids, child_bom_name,
                               product_name, workstep_column, amount_join, product_join),
                               ([type, src_ctx, src_ctx, tgt_ctx, tgt_ctx]))

        return request.env.cr.dictfetchall()