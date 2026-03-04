# -*- coding: utf-8 -*-
# from odoo import http


# class OdooWhiteboard(http.Controller):
#     @http.route('/odoo_whiteboard/odoo_whiteboard', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/odoo_whiteboard/odoo_whiteboard/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('odoo_whiteboard.listing', {
#             'root': '/odoo_whiteboard/odoo_whiteboard',
#             'objects': http.request.env['odoo_whiteboard.odoo_whiteboard'].search([]),
#         })

#     @http.route('/odoo_whiteboard/odoo_whiteboard/objects/<model("odoo_whiteboard.odoo_whiteboard"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('odoo_whiteboard.object', {
#             'object': obj
#         })
