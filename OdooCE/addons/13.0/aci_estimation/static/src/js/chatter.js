odoo.define('estimation.mail.Chatter', function (require) {
"use strict";
const Chatter = require('mail/static/src/components/chatter_topbar/chatter_topbar.js');
var rpc = require('web.rpc');
var web_client = require('web.web_client');

Chatter.include({
    _onClickAllActivity: function () {
        var self = this;
        rpc.query({
             model: 'mail.activity',
             method: 'activity_tree_btn',
             args: [{}, 'all', this.record.model, this.record.res_id],
            }).then((action) => {
            if (action){
                web_client.do_action(action, {
                on_close: () => {
                    self._controller.reload();
                },
                })
            }else{
                self._controller.reload();
            }
        });
    },
    _onClickRestrictionActivity: function () {
        var self = this;
        rpc.query({
             model: 'mail.activity',
             method: 'activity_tree_btn',
             args: [{}, 'restriction', this.record.model, this.record.res_id],
            }).then((action) => {
            if (action){
                web_client.do_action(action, {
                on_close: () => {
                    self._controller.reload();
                },
                })
            }else{
                self._controller.reload();
            }
        });
    },
    _onClickNoncomplianceActivity: function () {
        var self = this;
        rpc.query({
             model: 'mail.activity',
             method: 'activity_tree_btn',
             args: [{}, 'noncompliance', this.record.model, this.record.res_id],
            }).then((action) => {
            if (action){
                web_client.do_action(action, {
                on_close: () => {
                    self._controller.reload();
                },
                })
            }else{
                self._controller.reload();
            }
        });
    },
    _onClickNonconformityActivity: function () {
        var self = this;
        rpc.query({
             model: 'mail.activity',
             method: 'activity_tree_btn',
             args: [{}, 'nonconformity', this.record.model, this.record.res_id],
            }).then((action) => {
            if (action){
                web_client.do_action(action, {
                on_close: () => {
                    self._controller.reload();
                },
                })
            }else{
                self._controller.reload();
            }
        });
    },_onClickConfiguratorActivity: function () {
        rpc.query({
             model: 'mail.activity',
             method: 'activity_configurator_btn',
             args: [{}, this.record.model, this.record.res_id],
            }).then((action) => {
            if (action){
                web_client.do_action(action)
            }
        });
    },


    })
});