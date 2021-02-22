odoo.define("aci_estimation.Dialog", function (require) {
"use strict";

var core = require('web.core');
var dom = require('web.dom');
var Widget = require('web.Widget');
var Dialog = require('web.Dialog');

var QWeb = core.qweb;
var _t = core._t;
/**
 *
 *
 */
const config = require("web.config");
    if (config.device.isMobile) {
        return;
    }

Dialog.include({
    init: function (parent, options) {
        var self = this;
        this._super(parent);
        this._opened = new Promise(function (resolve) {
            self._openedResolver = resolve;
        });

        options = _.defaults(options || {}, {
            title: _t('Odoo'), subtitle: '',
            size: 'large',
            fullscreen: false,
            dialogClass: '',
            $content: false,
            buttons: [{text: _t("Ok"), close: true}],
            technical: true,
            $parentNode: false,
            backdrop: 'static',
            renderHeader: true,
            renderFooter: true,
            onForceClose: false,
        });
        this.$content = options.$content;
        this.title = options.title;
        this.subtitle = options.subtitle;
        this.fullscreen = options.fullscreen;
        this.dialogClass = options.dialogClass;
        this.size = options.size;
        this.buttons = options.buttons;
        this.technical = options.technical;
        this.$parentNode = options.$parentNode;
        this.backdrop = options.backdrop;
        this.renderHeader = options.renderHeader;
        this.renderFooter = options.renderFooter;
        this.onForceClose = options.onForceClose;

//        SIZE
        var size = this.title.split("//");
        var sizes = ['small', 'large', 'extra-large'];
        if(sizes.includes(size[1])){
               this.title = size[0];
               this.size = size[1];}
        core.bus.on('close_dialogs', this, this.destroy.bind(this));
    },
});

});
