#!/usr/bin/env python3
"""Generate the Jitsi Videobridge Grafana dashboard JSON.

Single source of truth for dashboards/jitsi-jvb.json. Keeping the dashboard
as generated output avoids hand-editing thousands of lines of JSON and keeps
panel layout/IDs consistent. Targets Grafana 13+, jitsi-meet 10590+ (JVB
Prometheus /metrics, `jitsi_jvb_*` namespace).
"""
import json

DS = "${datasource}"
INST = '{instance=~"$instance"}'
RI = "$__rate_interval"

panels = []
_pid = [0]

# Current append target. Expanded rows keep panels as flat top-level siblings;
# collapsed rows must NEST their child panels inside the row's own "panels" array
# (a collapsed row with flat siblings is malformed and hides panels on expand).
_container = [panels]


def add(panel):
    _container[0].append(panel)


def pid():
    _pid[0] += 1
    return _pid[0]


# layout cursor ----------------------------------------------------------
class Grid:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.rowh = 0

    def place(self, w, h):
        if self.x + w > 24:
            self.x = 0
            self.y += self.rowh
            self.rowh = 0
        gp = {"h": h, "w": w, "x": self.x, "y": self.y}
        self.x += w
        self.rowh = max(self.rowh, h)
        return gp

    def newline(self):
        self.x = 0
        self.y += self.rowh
        self.rowh = 0


g = Grid()


def ds():
    return {"type": "prometheus", "uid": DS}


def target(expr, legend="", instant=False, fmt="time_series", refid="A"):
    t = {
        "datasource": ds(),
        "editorMode": "code",
        "expr": expr,
        "legendFormat": legend or "__auto",
        "range": not instant,
        "instant": instant,
        "refId": refid,
        "format": fmt,
    }
    return t


def targets(specs):
    out = []
    for i, s in enumerate(specs):
        refid = chr(ord("A") + i)
        out.append(target(s[0], s[1] if len(s) > 1 else "", refid=refid))
    return out


def row(title, collapsed=False):
    g.newline()
    gp = g.place(24, 1)
    r = {
        "type": "row",
        "title": title,
        "collapsed": collapsed,
        "gridPos": gp,
        "id": pid(),
        "panels": [],
    }
    panels.append(r)  # the row panel itself is always top-level
    # subsequent panels nest into the row when collapsed, else stay top-level
    _container[0] = r["panels"] if collapsed else panels
    g.newline()


def stat(title, expr, w=3, h=4, unit="none", decimals=None, mappings=None,
         thresholds=None, legend="", colormode="value", graphmode="none",
         instant=True, desc=""):
    gp = g.place(w, h)
    if thresholds is None:
        thresholds = [{"color": "text", "value": None}]
    fc = {
        "defaults": {
            "unit": unit,
            "mappings": mappings or [],
            "thresholds": {"mode": "absolute", "steps": thresholds},
            "color": {"mode": "thresholds"} if thresholds and len(thresholds) > 1 else {"mode": "fixed", "fixedColor": "text"},
        },
        "overrides": [],
    }
    if decimals is not None:
        fc["defaults"]["decimals"] = decimals
    add({
        "type": "stat", "title": title, "description": desc, "id": pid(),
        "gridPos": gp, "datasource": ds(),
        "targets": [target(expr, legend, instant=instant)],
        "fieldConfig": fc,
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto", "textMode": "auto", "colorMode": colormode,
            "graphMode": graphmode, "justifyMode": "auto", "showPercentChange": False,
        },
    })


def gauge(title, expr, w=3, h=4, unit="none", mn=0, mx=1, thresholds=None,
          decimals=2, desc=""):
    gp = g.place(w, h)
    if thresholds is None:
        thresholds = [
            {"color": "green", "value": None},
            {"color": "yellow", "value": 0.6},
            {"color": "red", "value": 0.85},
        ]
    add({
        "type": "gauge", "title": title, "description": desc, "id": pid(),
        "gridPos": gp, "datasource": ds(),
        "targets": [target(expr, "", instant=True)],
        "fieldConfig": {"defaults": {
            "unit": unit, "min": mn, "max": mx, "decimals": decimals,
            "mappings": [],
            "thresholds": {"mode": "absolute", "steps": thresholds},
            "color": {"mode": "thresholds"},
        }, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto", "showThresholdLabels": False, "showThresholdMarkers": True,
        },
    })


def timeseries(title, specs, w=12, h=8, unit="none", desc="", stack=False,
               fill=10, legend_table=False, decimals=None, mn=None):
    gp = g.place(w, h)
    custom = {
        "drawStyle": "line", "lineInterpolation": "smooth", "lineWidth": 1,
        "fillOpacity": fill, "gradientMode": "opacity", "spanNulls": True,
        "showPoints": "never", "pointSize": 5,
        "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        "axisPlacement": "auto", "axisColorMode": "text", "scaleDistribution": {"type": "linear"},
    }
    defaults = {
        "unit": unit, "custom": custom, "mappings": [],
        "color": {"mode": "palette-classic"},
        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
    }
    if decimals is not None:
        defaults["decimals"] = decimals
    if mn is not None:
        defaults["min"] = mn
    legend = {"displayMode": "table" if legend_table else "list",
              "placement": "bottom",
              "calcs": ["lastNotNull", "max"] if legend_table else [],
              "showLegend": True}
    add({
        "type": "timeseries", "title": title, "description": desc, "id": pid(),
        "gridPos": gp, "datasource": ds(),
        "targets": targets(specs),
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"legend": legend, "tooltip": {"mode": "multi", "sort": "desc"}},
    })


def heatmap(title, bucket_metric, w=8, h=9, unit="short", desc=""):
    gp = g.place(w, h)
    expr = "sum(increase(jitsi_jvb_%s_bucket%s[$__rate_interval])) by (le)" % (bucket_metric, INST)
    t = target(expr, "{{le}}", fmt="heatmap")
    t["format"] = "heatmap"
    add({
        "type": "heatmap", "title": title, "description": desc, "id": pid(),
        "gridPos": gp, "datasource": ds(),
        "targets": [t],
        "options": {
            "calculate": False,
            "cellGap": 1,
            "cellValues": {"unit": "short"},
            "color": {"scheme": "Spectral", "mode": "scheme", "steps": 64,
                       "reverse": True, "exponent": 0.5, "fill": "dark-orange"},
            "yAxis": {"unit": "short", "axisPlacement": "left", "decimals": 0},
            "rowsFrame": {"layout": "auto", "value": "Conferences"},
            "tooltip": {"mode": "single", "yHistogram": True, "show": True},
            "legend": {"show": True},
            "exemplars": {"color": "rgba(255,0,255,0.7)"},
            "filterValues": {"le": 1e-9},
        },
        "fieldConfig": {"defaults": {"custom": {"hideFrom": {"tooltip": False, "viz": False, "legend": False}}, "scaleDistribution": {"type": "linear"}}, "overrides": []},
    })


# =======================================================================
# OVERVIEW & HEALTH
# =======================================================================
row("Overview & Health")

stat("Healthy", "min(jitsi_jvb_healthy%s)" % INST, w=3,
     mappings=[{"type": "value", "options": {
         "0": {"text": "UNHEALTHY", "color": "red", "index": 0},
         "1": {"text": "Healthy", "color": "green", "index": 1}}}],
     thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}],
     colormode="background", desc="jitsi_jvb_healthy: whether the bridge instance is healthy.")
gauge("Stress", "max(jitsi_jvb_stress%s)" % INST, w=3, mn=0, mx=1,
      desc="jitsi_jvb_stress: current stress level (0..1).")
gauge("CPU steal", "max(jitsi_jvb_cpu_steal%s)" % INST, w=3, mn=0, mx=1,
      desc="jitsi_jvb_cpu_steal: CPU steal fraction (0..1).")
stat("Conferences", "sum(jitsi_jvb_conferences%s)" % INST, w=3, colormode="value",
     thresholds=[{"color": "blue", "value": None}], graphmode="area", instant=False,
     desc="jitsi_jvb_conferences: current number of conferences.")
stat("Participants", "sum(jitsi_jvb_local_endpoints%s)" % INST, w=3, colormode="value",
     thresholds=[{"color": "blue", "value": None}], graphmode="area", instant=False,
     desc="jitsi_jvb_local_endpoints: local endpoints currently on the bridge(s).")
stat("Visitors", "sum(jitsi_jvb_current_visitors%s)" % INST, w=3,
     thresholds=[{"color": "purple", "value": None}],
     desc="jitsi_jvb_current_visitors: current visitor endpoints.")
stat("Largest conference", "max(jitsi_jvb_largest_conference%s)" % INST, w=3,
     thresholds=[{"color": "text", "value": None}],
     desc="jitsi_jvb_largest_conference: endpoints in the largest conference.")
stat("Bridges up", "count(jitsi_jvb_healthy%s)" % INST, w=3,
     thresholds=[{"color": "text", "value": None}],
     desc="Number of JVB instances currently scraped.")

# line B
# startup_time is exposed as epoch MILLISECONDS, so divide by 1000 for uptime seconds.
stat("Uptime", "max(time() - jitsi_jvb_startup_time%s/1000)" % INST, w=3, unit="s",
     thresholds=[{"color": "text", "value": None}],
     desc="Derived from jitsi_jvb_startup_time.")
stat("Drain mode", "max(jitsi_jvb_drain_mode%s)" % INST, w=3,
     mappings=[{"type": "value", "options": {
         "0": {"text": "Off", "color": "green", "index": 0},
         "1": {"text": "DRAINING", "color": "orange", "index": 1}}}],
     thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}],
     colormode="background", desc="jitsi_jvb_drain_mode.")
stat("Graceful shutdown", "max(jitsi_jvb_graceful_shutdown%s)" % INST, w=3,
     mappings=[{"type": "value", "options": {
         "0": {"text": "No", "color": "green", "index": 0},
         "1": {"text": "YES", "color": "orange", "index": 1}}}],
     thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}],
     colormode="background", desc="jitsi_jvb_graceful_shutdown.")
stat("Shutting down", "max(jitsi_jvb_shutting_down%s)" % INST, w=3,
     mappings=[{"type": "value", "options": {
         "0": {"text": "No", "color": "green", "index": 0},
         "1": {"text": "YES", "color": "red", "index": 1}}}],
     thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
     colormode="background", desc="jitsi_jvb_shutting_down.")
stat("Download", "sum(jitsi_jvb_incoming_bitrate%s)" % INST, w=3, unit="bps",
     thresholds=[{"color": "green", "value": None}], graphmode="area", instant=False,
     desc="jitsi_jvb_incoming_bitrate (bps).")
stat("Upload", "sum(jitsi_jvb_outgoing_bitrate%s)" % INST, w=3, unit="bps",
     thresholds=[{"color": "green", "value": None}], graphmode="area", instant=False,
     desc="jitsi_jvb_outgoing_bitrate (bps).")
stat("Packet loss", "max(jitsi_jvb_loss_fraction%s)" % INST, w=3, unit="percentunit",
     decimals=2,
     thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 0.02}, {"color": "red", "value": 0.1}],
     colormode="value", desc="jitsi_jvb_loss_fraction: combined in/out RTP loss.")
stat("Avg RTT", "max(jitsi_jvb_average_rtt%s)" % INST, w=3, unit="ms", decimals=1,
     thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 150}, {"color": "red", "value": 300}],
     colormode="value", desc="jitsi_jvb_average_rtt: avg RTT across local endpoints (ms).")

# =======================================================================
# CONFERENCES & ENDPOINTS
# =======================================================================
row("Conferences & Endpoints", collapsed=False)

timeseries("Conferences", [
    ("sum(jitsi_jvb_conferences%s)" % INST, "total"),
    ("sum(jitsi_jvb_conferences_inactive%s)" % INST, "inactive"),
    ("sum(jitsi_jvb_conferences_p2p%s)" % INST, "p2p"),
    ("sum(jitsi_jvb_conferences_with_relay%s)" % INST, "with relay"),
    ("max(jitsi_jvb_largest_conference%s)" % INST, "largest"),
], desc="Current conferences broken down by state.")

timeseries("Conference churn (per min)", [
    ("sum(rate(jitsi_jvb_conferences_created%s[%s]))*60" % (INST, RI), "created/min"),
    ("sum(rate(jitsi_jvb_conferences_completed%s[%s]))*60" % (INST, RI), "completed/min"),
], desc="Rate of conferences_created / conferences_completed.")

timeseries("Endpoints", [
    ("sum(jitsi_jvb_current_endpoints%s)" % INST, "current (local+relayed)"),
    ("sum(jitsi_jvb_local_endpoints%s)" % INST, "local"),
    ("sum(jitsi_jvb_active_endpoints%s)" % INST, "active"),
    ("sum(jitsi_jvb_endpoints_inactive%s)" % INST, "inactive"),
    ("sum(jitsi_jvb_endpoints_relayed%s)" % INST, "relayed"),
], desc="Endpoint counts by state.")

timeseries("Senders & special endpoints", [
    ("sum(jitsi_jvb_endpoints_sending_audio%s)" % INST, "sending audio"),
    ("sum(jitsi_jvb_endpoints_sending_video%s)" % INST, "sending video"),
    ("sum(jitsi_jvb_endpoints_recvonly%s)" % INST, "recv-only"),
    ("sum(jitsi_jvb_endpoints_oversending%s)" % INST, "oversending"),
    ("sum(jitsi_jvb_endpoints_with_suspended_sources%s)" % INST, "suspended sources"),
], desc="Local endpoints by sending behaviour.")

# =======================================================================
# CONFERENCE SIZE DISTRIBUTION (Prometheus histograms — not in JSON stats)
# =======================================================================
row("Conference Size Distribution (Prometheus histograms)", collapsed=False)

heatmap("Conferences by size (endpoints)", "conferences_by_size",
        desc="jitsi_jvb_conferences_by_size histogram. Distribution of conference sizes over time. NOT available via the JSON /colibri/stats endpoint.")
heatmap("Conferences by audio senders", "conferences_by_audio_sender",
        desc="jitsi_jvb_conferences_by_audio_sender histogram.")
heatmap("Conferences by video senders", "conferences_by_video_sender",
        desc="jitsi_jvb_conferences_by_video_sender histogram.")

g.newline()
timeseries("Conference size quantiles (endpoints)", [
    ("histogram_quantile(0.5, sum(rate(jitsi_jvb_conferences_by_size_bucket%s[%s])) by (le))" % (INST, RI), "p50"),
    ("histogram_quantile(0.9, sum(rate(jitsi_jvb_conferences_by_size_bucket%s[%s])) by (le))" % (INST, RI), "p90"),
    ("histogram_quantile(0.99, sum(rate(jitsi_jvb_conferences_by_size_bucket%s[%s])) by (le))" % (INST, RI), "p99"),
], w=8, h=7, desc="Quantiles derived from the conferences_by_size histogram.")
timeseries("Audio-sender quantiles", [
    ("histogram_quantile(0.5, sum(rate(jitsi_jvb_conferences_by_audio_sender_bucket%s[%s])) by (le))" % (INST, RI), "p50"),
    ("histogram_quantile(0.9, sum(rate(jitsi_jvb_conferences_by_audio_sender_bucket%s[%s])) by (le))" % (INST, RI), "p90"),
    ("histogram_quantile(0.99, sum(rate(jitsi_jvb_conferences_by_audio_sender_bucket%s[%s])) by (le))" % (INST, RI), "p99"),
], w=8, h=7, desc="Quantiles derived from conferences_by_audio_sender.")
timeseries("Video-sender quantiles", [
    ("histogram_quantile(0.5, sum(rate(jitsi_jvb_conferences_by_video_sender_bucket%s[%s])) by (le))" % (INST, RI), "p50"),
    ("histogram_quantile(0.9, sum(rate(jitsi_jvb_conferences_by_video_sender_bucket%s[%s])) by (le))" % (INST, RI), "p90"),
    ("histogram_quantile(0.99, sum(rate(jitsi_jvb_conferences_by_video_sender_bucket%s[%s])) by (le))" % (INST, RI), "p99"),
], w=8, h=7, desc="Quantiles derived from conferences_by_video_sender.")

# =======================================================================
# TRAFFIC
# =======================================================================
row("Traffic", collapsed=False)

timeseries("Bitrate", [
    ("sum(jitsi_jvb_incoming_bitrate%s)" % INST, "incoming"),
    ("sum(jitsi_jvb_outgoing_bitrate%s)" % INST, "outgoing"),
], unit="bps", desc="Aggregate RTP/RTCP bitrate (jitsi_jvb_incoming_bitrate / outgoing_bitrate).")

timeseries("Packet rate", [
    ("sum(jitsi_jvb_incoming_packet_rate%s)" % INST, "incoming"),
    ("sum(jitsi_jvb_outgoing_packet_rate%s)" % INST, "outgoing"),
], unit="pps", desc="jitsi_jvb_incoming_packet_rate / outgoing_packet_rate.")

timeseries("Throughput (bytes/s)", [
    ("sum(rate(jitsi_jvb_bytes_received%s[%s]))" % (INST, RI), "received"),
    ("sum(rate(jitsi_jvb_bytes_sent%s[%s]))" % (INST, RI), "sent"),
], unit="Bps", desc="rate of jitsi_jvb_bytes_received / bytes_sent counters.")

timeseries("Packets/s & data-channel msgs/s", [
    ("sum(rate(jitsi_jvb_packets_received%s[%s]))" % (INST, RI), "packets recv"),
    ("sum(rate(jitsi_jvb_packets_sent%s[%s]))" % (INST, RI), "packets sent"),
    ("sum(rate(jitsi_jvb_data_channel_messages_received%s[%s]))" % (INST, RI), "dc msgs recv"),
    ("sum(rate(jitsi_jvb_data_channel_messages_sent%s[%s]))" % (INST, RI), "dc msgs sent"),
], unit="cps", desc="Counter rates for packets and data-channel messages.")

# =======================================================================
# QUALITY & RELIABILITY
# =======================================================================
row("Quality & Reliability", collapsed=False)

timeseries("Loss fraction", [
    ("max(jitsi_jvb_incoming_loss_fraction%s)" % INST, "incoming"),
    ("max(jitsi_jvb_outgoing_loss_fraction%s)" % INST, "outgoing"),
    ("max(jitsi_jvb_loss_fraction%s)" % INST, "combined"),
], unit="percentunit", decimals=3, mn=0, desc="RTP loss fractions (0..1).")

timeseries("Average RTT", [
    ("max(jitsi_jvb_average_rtt%s)" % INST, "avg rtt"),
], unit="ms", desc="jitsi_jvb_average_rtt across local endpoints.")

timeseries("Problem endpoints", [
    ("sum(jitsi_jvb_endpoints_with_high_outgoing_loss%s)" % INST, "high outgoing loss"),
    ("sum(jitsi_jvb_endpoints_with_suspended_sources%s)" % INST, "suspended sources"),
    ("sum(jitsi_jvb_endpoints_with_spurious_remb%s)" % INST, "spurious REMB"),
], desc="Endpoints in degraded states.")

timeseries("ICE / DTLS (per min)", [
    ("sum(rate(jitsi_jvb_ice_succeeded%s[%s]))*60" % (INST, RI), "ice succeeded"),
    ("sum(rate(jitsi_jvb_ice_succeeded_relayed%s[%s]))*60" % (INST, RI), "ice succeeded (relayed)"),
    ("sum(rate(jitsi_jvb_ice_failed%s[%s]))*60" % (INST, RI), "ice failed"),
    ("sum(rate(jitsi_jvb_endpoints_dtls_failed%s[%s]))*60" % (INST, RI), "dtls failed"),
], desc="ICE/DTLS connectivity establishment rates.")

timeseries("Endpoint connectivity events (per min)", [
    ("sum(rate(jitsi_jvb_endpoints_disconnected%s[%s]))*60" % (INST, RI), "disconnected"),
    ("sum(rate(jitsi_jvb_endpoints_reconnected%s[%s]))*60" % (INST, RI), "reconnected"),
    ("sum(rate(jitsi_jvb_endpoints_no_message_transport_after_delay%s[%s]))*60" % (INST, RI), "no msg transport"),
], desc="Endpoint disconnect/reconnect activity.")

timeseries("Media events (per min)", [
    ("sum(rate(jitsi_jvb_keyframes_received%s[%s]))*60" % (INST, RI), "keyframes recv"),
    ("sum(rate(jitsi_jvb_dominant_speaker_changes%s[%s]))*60" % (INST, RI), "dominant speaker changes"),
    ("sum(rate(jitsi_jvb_layering_changes_received%s[%s]))*60" % (INST, RI), "layering changes"),
    ("sum(rate(jitsi_jvb_preemptive_keyframe_requests_sent%s[%s]))*60" % (INST, RI), "preemptive KFR sent"),
    ("sum(rate(jitsi_jvb_preemptive_keyframe_requests_suppressed%s[%s]))*60" % (INST, RI), "preemptive KFR suppressed"),
], desc="Keyframe, speaker and layering activity.")

# =======================================================================
# RELAY (Octo)
# =======================================================================
row("Relay (Octo)", collapsed=True)

timeseries("Relay bitrate", [
    ("sum(jitsi_jvb_relay_incoming_bitrate%s)" % INST, "incoming"),
    ("sum(jitsi_jvb_relay_outgoing_bitrate%s)" % INST, "outgoing"),
], unit="bps", desc="Bitrate to/from relays.")
timeseries("Relay packet rate", [
    ("sum(jitsi_jvb_relay_incoming_packet_rate%s)" % INST, "incoming"),
    ("sum(jitsi_jvb_relay_outgoing_packet_rate%s)" % INST, "outgoing"),
], unit="pps", desc="Packet rate to/from relays.")
timeseries("Relays & relayed endpoints", [
    ("sum(jitsi_jvb_conferences_with_relay%s)" % INST, "conferences with relay"),
    ("sum(jitsi_jvb_endpoints_relayed%s)" % INST, "relayed endpoints"),
    ("sum(rate(jitsi_jvb_relays%s[%s]))*60" % (INST, RI), "relays created/min"),
], desc="Relay topology.")
timeseries("Relay throughput", [
    ("sum(rate(jitsi_jvb_relay_bytes_received%s[%s]))" % (INST, RI), "bytes recv"),
    ("sum(rate(jitsi_jvb_relay_bytes_sent%s[%s]))" % (INST, RI), "bytes sent"),
], unit="Bps", desc="Relay byte throughput.")

# =======================================================================
# JVM & SYSTEM
# =======================================================================
row("JVM & System", collapsed=True)

timeseries("JVM heap", [
    ("sum(jitsi_jvb_jvm_heap_used%s)" % INST, "used"),
    ("sum(jitsi_jvb_jvm_heap_committed%s)" % INST, "committed"),
], unit="decbytes", desc="jitsi_jvb_jvm_heap_used / committed.")
timeseries("Garbage collection", [
    ("max(jitsi_jvb_jvm_gc_count%s)" % INST, "gc count"),
    ("max(jitsi_jvb_jvm_gc_time%s)" % INST, "gc time (ms)"),
], desc="jitsi_jvb_jvm_gc_count / gc_time.")
timeseries("Threads & file descriptors", [
    ("max(jitsi_jvb_thread_count%s)" % INST, "threads"),
    ("max(jitsi_jvb_jvm_open_fd_count%s)" % INST, "open fds"),
], desc="jitsi_jvb_thread_count / jvm_open_fd_count.")
timeseries("Stress & CPU steal", [
    ("max(jitsi_jvb_stress%s)" % INST, "stress"),
    ("max(jitsi_jvb_cpu_steal%s)" % INST, "cpu steal"),
], unit="percentunit", mn=0, decimals=3, desc="jitsi_jvb_stress / cpu_steal (0..1).")
timeseries("Queue & RTP pipeline errors (per min)", [
    ("sum(rate(jitsi_jvb_queue_dropped_packets%s[%s]))*60" % (INST, RI), "queue dropped pkts"),
    ("sum(rate(jitsi_jvb_queue_exceptions%s[%s]))*60" % (INST, RI), "queue exceptions"),
    ("sum(rate(jitsi_jvb_rtp_sender_dropped_packets%s[%s]))*60" % (INST, RI), "rtp sender dropped"),
    ("sum(rate(jitsi_jvb_rtp_receiver_dropped_packets%s[%s]))*60" % (INST, RI), "rtp receiver dropped"),
    ("sum(rate(jitsi_jvb_rtp_sender_exceptions%s[%s]))*60" % (INST, RI), "rtp sender exceptions"),
    ("sum(rate(jitsi_jvb_rtp_receiver_exceptions%s[%s]))*60" % (INST, RI), "rtp receiver exceptions"),
], w=24, desc="Packet-pipeline drops and exceptions. Sustained non-zero values indicate an overloaded bridge.")

# =======================================================================
# XMPP & SIGNALING
# =======================================================================
row("XMPP & Signaling", collapsed=True)

timeseries("MUC clients", [
    ("sum(jitsi_jvb_muc_clients_configured%s)" % INST, "clients configured"),
    ("sum(jitsi_jvb_muc_clients_connected%s)" % INST, "clients connected"),
    ("sum(jitsi_jvb_mucs_connected%s)" % INST, "mucs connected"),
    ("sum(jitsi_jvb_mucs_joined%s)" % INST, "mucs joined"),
], desc="XMPP MUC client/connection counts.")
timeseries("XMPP disconnects (per min)", [
    ("sum(rate(jitsi_jvb_xmpp_disconnects%s[%s]))*60" % (INST, RI), "disconnects/min"),
], desc="rate of jitsi_jvb_xmpp_disconnects.")
timeseries("Colibri WebSocket messages (per min)", [
    ("sum(rate(jitsi_jvb_colibri_web_socket_messages_received%s[%s]))*60" % (INST, RI), "received"),
    ("sum(rate(jitsi_jvb_colibri_web_socket_messages_sent%s[%s]))*60" % (INST, RI), "sent"),
], desc="Colibri WS message throughput.")
timeseries("Colibri WebSocket errors & closes (per min)", [
    ("sum(rate(jitsi_jvb_colibri_web_socket_error%s[%s]))*60" % (INST, RI), "errors"),
    ("sum(rate(jitsi_jvb_colibri_web_socket_close_normal%s[%s]))*60" % (INST, RI), "close normal"),
    ("sum(rate(jitsi_jvb_colibri_web_socket_close_abnormal%s[%s]))*60" % (INST, RI), "close abnormal"),
], desc="Colibri WS error and close events.")


# =======================================================================
# COUNTER FIX-UP
# The JVB exposes Prometheus *counters* with a `_total` suffix on the series
# name (e.g. jitsi_jvb_bytes_received_total), while the `# TYPE` family name has
# no suffix. We reference counters by their family name immediately followed by
# `{` (the instance selector), so appending `_total` before that `{` is an
# unambiguous, full-name-boundary replacement. Gauges/histograms are untouched.
COUNTERS = [
    "endpoints_dtls_failed", "queue_dropped_packets", "preemptive_keyframe_requests_sent",
    "data_channel_messages_received", "relay_packets_sent", "dominant_speaker_changes",
    "ice_succeeded", "relay_packets_received", "relays", "relay_bytes_received",
    "rtp_sender_exceptions", "relay_bytes_sent", "colibri_web_socket_messages_received",
    "bytes_received", "conferences_completed", "colibri_web_socket_close_normal",
    "keyframes_received", "ice_failed", "colibri_web_socket_error", "endpoints_reconnected",
    "rtp_receiver_dropped_packets", "endpoints_disconnected", "colibri_web_socket_close_abnormal",
    "layering_changes_received", "packets_received", "conference_seconds",
    "colibri_web_socket_messages_sent", "xmpp_disconnects",
    "endpoints_no_message_transport_after_delay", "bytes_sent", "rtp_receiver_exceptions",
    "conferences_created", "packets_sent", "relays_no_message_transport_after_delay",
    "data_channel_messages_sent", "queue_exceptions", "visitors", "video_milliseconds_received",
    "rtp_sender_dropped_packets", "preemptive_keyframe_requests_suppressed", "endpoints",
    "ice_succeeded_relayed",
]


def _fixup_counters(panel):
    for t in panel.get("targets", []):
        expr = t["expr"]
        for name in COUNTERS:
            expr = expr.replace("jitsi_jvb_%s{" % name, "jitsi_jvb_%s_total{" % name)
        t["expr"] = expr


for _p in panels:
    _fixup_counters(_p)
    for _c in _p.get("panels", []):  # nested panels inside collapsed rows
        _fixup_counters(_c)

# =======================================================================
# DASHBOARD WRAPPER
# =======================================================================
dashboard = {
    "annotations": {"list": [{
        "builtIn": 1,
        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
        "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts", "type": "dashboard",
    }]},
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "links": [],
    "liveNow": False,
    "refresh": "30s",
    "schemaVersion": 39,
    "tags": ["jitsi", "jvb", "videobridge", "webrtc"],
    "templating": {"list": [
        {
            "name": "datasource", "label": "Data source", "type": "datasource",
            "query": "prometheus", "current": {}, "hide": 0, "refresh": 1,
            "regex": "", "includeAll": False, "multi": False,
        },
        {
            "name": "instance", "label": "JVB instance", "type": "query",
            "datasource": {"type": "prometheus", "uid": DS},
            "definition": "label_values(jitsi_jvb_healthy, instance)",
            "query": {"qryType": 1, "query": "label_values(jitsi_jvb_healthy, instance)", "refId": "StandardVariableQuery"},
            "current": {}, "hide": 0, "refresh": 2, "regex": "",
            "includeAll": True, "allValue": ".*", "multi": True,
            "sort": 1,
        },
    ]},
    "time": {"from": "now-6h", "to": "now"},
    "timepicker": {},
    "timezone": "browser",
    "title": "Jitsi Videobridge",
    "uid": "jitsi-jvb",
    "version": 1,
    "weekStart": "",
    "panels": panels,
}

with open("dashboards/jitsi-jvb.json", "w") as f:
    json.dump(dashboard, f, indent=2)
    f.write("\n")

print("panels:", len([p for p in panels if p["type"] != "row"]),
      "rows:", len([p for p in panels if p["type"] == "row"]))
