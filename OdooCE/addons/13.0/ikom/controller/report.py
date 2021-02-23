from odoo import http
from odoo.http import request, content_disposition, route


class IkomLotReport(http.Controller):

    @route(['/web/download/lot_report'], type='http', auth="user")
    def download_pdf(self, **kw):
        line_ids = request.env['sale.order.line'].sudo().search([('package_id', '!=', False)])
        if not line_ids:
            return None
        pdf, _ = request.env.ref('ikom.action_report_ikom_lot').sudo().render_qweb_pdf(line_ids.ids)
        pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)),
                          ('Content-Disposition', content_disposition('ikom_lot_report.PDF'))]
        return request.make_response(pdf, headers=pdfhttpheaders)