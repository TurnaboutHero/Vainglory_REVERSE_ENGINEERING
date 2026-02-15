#!/usr/bin/env python3
"""
VG:CE MITM Traffic Capture Addon for mitmproxy.
Usage: mitmdump -s vg/tools/mitm_capture.py --set output_dir=./captures
"""
import json
import os
from datetime import datetime
from mitmproxy import http, ctx

# Frida SSL Bypass reference snippet
FRIDA_SSL_BYPASS_JS = """
Java.perform(function() {
    var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
    TrustManagerImpl.verifyChain.implementation = function() {
        return Java.use('java.util.ArrayList').$new();
    };
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List')
            .implementation = function() { return; };
    } catch(e) {}
});
"""

VG_KEYWORDS = ["superevilmegacorp", "vainglorygame", "vainglory", "semc"]

class VGCaptureAddon:
    def __init__(self):
        self.capture_count = 0
        self.output_dir = "./captures"
        self.captures = []

    def load(self, loader):
        loader.add_option("output_dir", str, "./captures", "Output directory for captures")

    def configure(self, updates):
        self.output_dir = ctx.options.output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _is_vg_traffic(self, flow: http.HTTPFlow) -> bool:
        host = flow.request.pretty_host.lower()
        return any(kw in host for kw in VG_KEYWORDS)

    def response(self, flow: http.HTTPFlow):
        if not self._is_vg_traffic(flow):
            return
        self.capture_count += 1
        entry = {
            "timestamp": datetime.now().isoformat(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "host": flow.request.pretty_host,
            "status_code": flow.response.status_code,
            "request_headers": dict(flow.request.headers),
            "response_headers": dict(flow.response.headers),
            "request_content_type": flow.request.headers.get("content-type", ""),
            "response_content_type": flow.response.headers.get("content-type", ""),
        }
        # Try to capture body as text/json
        try:
            req_text = flow.request.get_text()
            if req_text:
                try:
                    entry["request_body"] = json.loads(req_text)
                except (json.JSONDecodeError, ValueError):
                    entry["request_body"] = req_text[:2000]
        except Exception:
            entry["request_body"] = None

        try:
            resp_text = flow.response.get_text()
            if resp_text:
                try:
                    entry["response_body"] = json.loads(resp_text)
                except (json.JSONDecodeError, ValueError):
                    entry["response_body"] = resp_text[:5000]
        except Exception:
            entry["response_body"] = None

        self.captures.append(entry)
        ctx.log.info(f"[VG] #{self.capture_count} {entry['method']} {entry['url']} -> {entry['status_code']}")

        # Save periodically
        if self.capture_count % 10 == 0:
            self._save()

    def done(self):
        self._save()
        ctx.log.info(f"[VG] Total captures: {self.capture_count}")

    def _save(self):
        if not self.captures:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.output_dir, f"vg_capture_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.captures, f, indent=2, ensure_ascii=False)
        ctx.log.info(f"[VG] Saved {len(self.captures)} captures to {path}")

addons = [VGCaptureAddon()]
