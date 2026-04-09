import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import polars as pl
from datetime import datetime
import re

st.set_page_config(
    page_title="Wohnungsqualität Score",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .metric-card {
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .score-high {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
    }
    .score-medium {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
    }
    .score-low {
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "search_result" not in st.session_state:
    st.session_state.search_result = None
if "last_address" not in st.session_state:
    st.session_state.last_address = None
if "weights" not in st.session_state:
    st.session_state.weights = {
        "supermarket": 0.3,
        "doctor": 0.2,
        "public_transport": 0.3,
        "park": 0.2,
    }
if "workplace_weight" not in st.session_state:
    st.session_state.workplace_weight = 0.2
if "workplace_address" not in st.session_state:
    st.session_state.workplace_address = ""
if "radius" not in st.session_state:
    st.session_state.radius = 1500
if "pinned_results" not in st.session_state:
    st.session_state.pinned_results = []

# Farben für gepinnte Suchradien (unterschiedliche Farben für bis zu 10 gepinnte Ergebnisse)
PINNED_RADIUS_COLORS = [
    "#FF6B6B",  # Rot
    "#4ECDC4",  # Türkis
    "#95E1D3",  # Minze
    "#F38181",  # Rosé
    "#AA96DA",  # Lavendel
    "#FCBAD3",  # Pink
    "#A8D8EA",  # Hellblau
    "#AA96DA",  # Lila
    "#FFD3B6",  # Pfirsich
    "#FFAAA5",  # Korallenrot
]

API_BASE_URL = st.secrets.get("API_BASE_URL", "http://localhost:8000")

CATEGORY_NAMES = {
    "supermarket": "🛒 Supermärkte",
    "doctor": "👨‍⚕️ Medizinische Einrichtungen",
    "public_transport": "🚌 Öffentliche Verkehrsmittel",
    "park": "🌳 Parks",
    "workplace": "💼 Arbeitsplatz",
}

CATEGORY_ICONS = {
    "supermarket": "shopping-cart",
    "doctor": "heartbeat",
    "public_transport": "bus",
    "park": "tree",
}

COLOR_MAPPING = {
    "supermarket": "#FF6B6B",
    "doctor": "#733FC7A9",
    "public_transport": "#45B7D1",
    "park": "#0A5934C3",
    "workplace": "#FFA726",
}


def format_radius(radius_meters):
    if radius_meters >= 1000:
        return f"{radius_meters / 1000:.1f} km"
    else:
        return f"{radius_meters} m"


def fix_address_format(address_str):
    if not address_str:
        return address_str

    match = re.match(r"^(\d+[a-zA-Z]*)\s+(.+)$", address_str.strip())
    if match:
        return f"{match.group(2)} {match.group(1)}"
    return address_str


def get_score_color(score):
    if score >= 70:
        return "score-high"
    elif score >= 40:
        return "score-medium"
    else:
        return "score-low"


def score_to_emoji(score):
    if score >= 80:
        return "✅"
    elif score >= 60:
        return "👍"
    elif score >= 40:
        return "⚠️"
    else:
        return "❌"


def fetch_score(
    address, weights, radius, workplace_address=None, workplace_weight=None
):
    try:
        payload = {
            "address": address,
            "weights": weights,
            "radius": radius,
            "workplace_address": workplace_address,
            "workplace_weight": workplace_weight,
        }
        response = requests.post(f"{API_BASE_URL}/api/score", json=payload, timeout=20)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        st.error(
            "⏱️ **Timeout**: Die API antwortet zu langsam. "
            "Bitte versuchen Sie es später erneut oder reduzieren Sie den Suchradius."
        )
        return None

    except requests.exceptions.ConnectionError:
        st.error(
            f"❌ **Verbindungsfehler**: Kann keine Verbindung zur API unter "
            f"`{API_BASE_URL}` herstellen. Stellen Sie sicher, dass das Backend läuft."
        )
        return None

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.error(
                "📍 **Adresse nicht gefunden**: "
                "Bitte versuchen Sie eine andere Adresse oder ein anderes Format. "
                "Beispiel: 'Hauptstraße 10, Berlin' oder 'Berlin, Mitte'"
            )
        elif e.response.status_code == 500:
            st.error(
                "🔴 **Backend-Fehler**: "
                "Das Backend hat einen Fehler bei der Verarbeitung gehabt. "
                "Details: " + e.response.text[:200]
            )
        else:
            st.error(
                f"⚠️ **API Fehler ({e.response.status_code})**: {e.response.text[:300]}"
            )
        return None

    except requests.exceptions.RequestException as e:
        st.error(f"⚠️ **Netzwerkfehler**: {str(e)[:200]}")
        return None

    except Exception as e:
        st.error(f"🚨 **Unerwarteter Fehler**: {str(e)[:200]}")
        return None


def create_map(
    lat, lon, address_display, result, search_radius=1500, pinned_results=None
):
    if pinned_results is None:
        pinned_results = []

    m = folium.Map(location=[lat, lon], zoom_start=15, tiles="OpenStreetMap")

    # Aktueller Suchradius in Blau
    folium.Circle(
        location=[lat, lon],
        radius=search_radius,
        popup=f"Suchradius: {format_radius(search_radius)}",
        tooltip=f"Suchradius: {format_radius(search_radius)}",
        color="#45B7D1",
        fill=True,
        fillColor="#45B7D1",
        fillOpacity=0.15,
        weight=2,
    ).add_to(m)

    # Aktueller Suchstandort in Blau
    folium.Marker(
        location=[lat, lon],
        popup=f"<b>{address_display}</b><br>Suchstandort",
        tooltip=address_display,
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
    ).add_to(m)

    if result and result.get("workplace_lat") and result.get("workplace_lon"):
        folium.Marker(
            location=[result["workplace_lat"], result["workplace_lon"]],
            popup=f"<b>Arbeitsplatz</b><br>{result.get('workplace_address', 'Arbeitsplatz')}",
            tooltip="Arbeitsplatz",
            icon=folium.Icon(color="orange", icon="briefcase", prefix="fa"),
        ).add_to(m)

    # Aktuelle Suchergebnisse (POIs)
    if result and "details" in result:
        for detail in result["details"]:
            category = detail["category"]
            color = COLOR_MAPPING.get(category, "#95a5a6")

            if detail.get("nearby_pois"):
                for idx, poi in enumerate(detail["nearby_pois"]):
                    is_nearest_three = idx < 3
                    radius = 10 if is_nearest_three else 6
                    opacity = 0.8 if is_nearest_three else 0.5
                    weight = 2 if is_nearest_three else 1

                    folium.CircleMarker(
                        location=[poi["lat"], poi["lon"]],
                        radius=radius,
                        popup=f"<b>{CATEGORY_NAMES[category]}</b><br>Entfernung: {poi['distance']:.0f}m",
                        tooltip=f"{CATEGORY_NAMES[category]} - {poi['distance']:.0f}m",
                        color=color,
                        fill=True,
                        fillColor=color,
                        fillOpacity=opacity,
                        weight=weight,
                    ).add_to(m)

    # Gepinnte Suchradien und deren POIs mit unterschiedlichen Farben
    if pinned_results:
        for pinned_idx, pinned in enumerate(pinned_results):
            # Farbe für diesen gepinnten Radius
            radius_color = PINNED_RADIUS_COLORS[pinned_idx % len(PINNED_RADIUS_COLORS)]

            # Gepinnter Suchradius mit eigener Farbe
            if "radius" in pinned:
                folium.Circle(
                    location=[pinned["lat"], pinned["lon"]],
                    radius=pinned["radius"],
                    popup=f"📌 Gepinnter Suchradius: {format_radius(pinned['radius'])}",
                    tooltip=f"📌 {pinned['address']} - Radius: {format_radius(pinned['radius'])}",
                    color=radius_color,
                    fill=True,
                    fillColor=radius_color,
                    fillOpacity=0.1,
                    weight=2,
                    dashArray="5, 5",  # Gestrichelte Linie
                ).add_to(m)

            # Gepinnter Marker in Purple
            folium.Marker(
                location=[pinned["lat"], pinned["lon"]],
                popup=f"<b>📌 Gepinnt</b><br>{pinned['address']}<br>Score: {pinned['score']:.0f}/100",
                tooltip=f"Gepinnt: {pinned['address']}",
                icon=folium.Icon(color="purple", icon="map-pin", prefix="fa"),
            ).add_to(m)

            # POIs aus diesem gepinnten Suchradius anzeigen
            if "details" in pinned:
                for detail in pinned["details"]:
                    category = detail["category"]
                    poi_color = COLOR_MAPPING.get(category, "#95a5a6")

                    if detail.get("nearby_pois"):
                        for poi_idx, poi in enumerate(detail["nearby_pois"]):
                            is_nearest_three = poi_idx < 3
                            poi_radius = 6 if is_nearest_three else 4
                            poi_opacity = 0.5 if is_nearest_three else 0.3
                            poi_weight = 1 if is_nearest_three else 0.5

                            folium.CircleMarker(
                                location=[poi["lat"], poi["lon"]],
                                radius=poi_radius,
                                popup=f"<b>{CATEGORY_NAMES[category]}</b><br>Entfernung: {poi['distance']:.0f}m<br>(📌 Gepinnt)",
                                tooltip=f"{CATEGORY_NAMES[category]} - {poi['distance']:.0f}m (gepinnt)",
                                color=poi_color,
                                fill=True,
                                fillColor=poi_color,
                                fillOpacity=poi_opacity,
                                weight=poi_weight,
                            ).add_to(m)

    return m


st.title("🏠 Wohnungsqualität Score")
st.markdown(
    "Finden Sie die perfekte Lage, indem Sie bewerten, wie bequem eine Nachbarschaft für grundlegende Dienstleistungen ist."
)

with st.sidebar:
    st.header("⚙️ Einstellungen")

    st.subheader("🎯 Gewichtungspräferenzen")

    weights = {}
    total_weight_placeholder = st.empty()

    weights["supermarket"] = (
        st.slider(
            "Supermärkte",
            min_value=0,
            max_value=100,
            value=int(st.session_state.weights.get("supermarket", 0.3) * 100),
            step=5,
        )
        / 100.0
    )

    weights["doctor"] = (
        st.slider(
            "Medizinische Einrichtungen",
            min_value=0,
            max_value=100,
            value=int(st.session_state.weights.get("doctor", 0.2) * 100),
            step=5,
        )
        / 100.0
    )

    weights["public_transport"] = (
        st.slider(
            "Öffentliche Verkehrsmittel",
            min_value=0,
            max_value=100,
            value=int(st.session_state.weights.get("public_transport", 0.3) * 100),
            step=5,
        )
        / 100.0
    )

    weights["park"] = (
        st.slider(
            "Parks / Grünflächen",
            min_value=0,
            max_value=100,
            value=int(st.session_state.weights.get("park", 0.2) * 100),
            step=5,
        )
        / 100.0
    )

    total = sum(weights.values())
    total_percent = total * 100

    with total_weight_placeholder.container():
        if total_percent > 100:
            st.metric("Gesamtgewicht", f"{total_percent:.1f}%")
            st.error(
                f"❌ **Gewicht zu hoch!** Aktuell: {total_percent:.1f}%, Max: 100%\n\n"
                "Bitte reduzieren Sie die Schieberegler so, dass die Summe 100% nicht überschreitet."
            )
        elif total_percent < 100:
            st.metric("Gesamtgewicht", f"{total_percent:.1f}%")
            st.warning(
                f"⚠️ **Gewicht unter 100%!** Aktuell: {total_percent:.1f}%\n\n"
                "Die Gewichte werden proportional auf 100% normalisiert."
            )
        else:
            st.metric("Gesamtgewicht", f"{total_percent:.1f}%", delta="✅")

    st.session_state.weights = weights

    st.divider()

    st.subheader("💼 Arbeitsplatz (Optional)")

    workplace_address = st.text_input(
        "Arbeitsplatz-Adresse",
        value=st.session_state.workplace_address,
        placeholder="z.B. Hauptstraße 5, Berlin",
        label_visibility="collapsed",
        key="workplace_input",
    )

    prev_workplace = st.session_state.workplace_address
    st.session_state.workplace_address = workplace_address

    trigger_search_workplace = workplace_address != prev_workplace and workplace_address

    if workplace_address:
        st.session_state.workplace_weight = (
            st.slider(
                "Arbeitsplatz Gewichtung",
                min_value=0,
                max_value=100,
                value=int(st.session_state.workplace_weight * 100),
                step=5,
            )
            / 100.0
        )
        st.caption(f"Gewicht: {st.session_state.workplace_weight:.1%}")
    else:
        st.session_state.workplace_weight = 0.2
        st.caption("Adresse eingeben, um Arbeitsplatz einzubeziehen")

    st.divider()

    st.subheader("🔍 Suchradius")

    radius_options = {
        "250m": 250,
        "500m": 500,
        "750m": 750,
        "1 km": 1000,
        "1.5 km": 1500,
        "2 km": 2000,
        "3 km": 3000,
        "5 km": 5000,
        "10 km": 10000,
        "15 km": 15000,
        "30 km": 30000,
    }

    current_radius = st.session_state.radius
    current_label = next(
        (label for label, value in radius_options.items() if value == current_radius),
        "1.5 km",
    )

    prev_radius = st.session_state.radius

    selected_radius_label = st.selectbox(
        "Radius auswählen",
        options=list(radius_options.keys()),
        index=list(radius_options.keys()).index(current_label),
        label_visibility="collapsed",
        key="radius_selectbox",
    )

    selected_radius = radius_options[selected_radius_label]

    st.metric("Ausgewählter Radius", format_radius(selected_radius))

    trigger_search_radius = selected_radius != prev_radius
    st.session_state.radius = selected_radius

    # st.divider()

    # api_url = st.text_input(
    #     "API Basis-URL",
    #     value=API_BASE_URL,
    #     help="Die URL, unter der die Wohnungsqualität-API läuft",
    # )

    st.divider()
    st.markdown("### ℹ️ Über die App")
    st.info("""
    **Wohnungsqualität Score** bewertet Nachbarschaften basierend auf:
    - 🛒 Supermärkte
    - 👨‍⚕️ Medizinische Einrichtungen
    - 🚌 Öffentliche Verkehrsmittel
    - 🌳 Parks
    
    Passen Sie die Gewichtung an Ihre persönlichen Vorlieben an!
    """)

st.subheader("🔍 Standort durchsuchen")
col1, col2 = st.columns([4, 1])

with col1:
    address_input = st.text_input(
        "Geben Sie eine Adresse ein",
        placeholder="z.B. Campusallee 12, Lemgo",
        label_visibility="collapsed",
    )

with col2:
    search_button = st.button("🔍 Bewerten", width="stretch")


def perform_search(address_input, weights, radius, workplace_address, workplace_weight):
    search_container = st.container()

    with search_container:
        status_placeholder = st.empty()
        progress_placeholder = st.empty()

        status_placeholder.info(f"🔍 **Analysiere**: '{address_input}'...")
        progress_placeholder.progress(10)

        import time

        start_time = time.time()
        result = fetch_score(
            address_input,
            weights,
            radius,
            workplace_address=workplace_address if workplace_address else None,
            workplace_weight=workplace_weight if workplace_address else None,
        )
        elapsed = time.time() - start_time

        if result:
            status_placeholder.success(f"✅ **Analysiert** in {elapsed:.1f}s")
            progress_placeholder.progress(100)
            time.sleep(0.5)
            status_placeholder.empty()
            progress_placeholder.empty()

            st.session_state.search_result = result
            st.session_state.last_address = address_input
        else:
            status_placeholder.empty()
            progress_placeholder.empty()


auto_search_triggered = (
    trigger_search_workplace or trigger_search_radius
) and st.session_state.search_result

if search_button and address_input:
    perform_search(
        address_input,
        st.session_state.weights,
        st.session_state.radius,
        st.session_state.workplace_address,
        st.session_state.workplace_weight,
    )
elif auto_search_triggered and st.session_state.last_address:
    perform_search(
        st.session_state.last_address,
        st.session_state.weights,
        st.session_state.radius,
        st.session_state.workplace_address,
        st.session_state.workplace_weight,
    )

if st.session_state.search_result:
    result = st.session_state.search_result

    fixed_address = fix_address_format(result["address_display"])

    st.success(f"✅ Ergebnisse für: **{fixed_address}**")

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.caption(f"📍 Koordinaten: {result['lat']:.4f}, {result['lon']:.4f}")
    with col_info2:
        st.caption(f"🔍 Suchradius: {format_radius(st.session_state.radius)}")

    st.divider()

    st.subheader("📊 Gesamtbewertung")
    score = result["total_score"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Punktzahl",
            f"{score}/100",
            delta=f"{score_to_emoji(score)}",
            delta_color="off",
        )

    with col2:
        st.metric("Breite", f"{result['lat']:.4f}")

    with col3:
        st.metric("Länge", f"{result['lon']:.4f}")

    st.divider()

    st.subheader("🗺️ Standortkarte & Suchradius")

    m = create_map(
        result["lat"],
        result["lon"],
        fixed_address,
        result,
        st.session_state.radius,
        pinned_results=st.session_state.pinned_results,
    )
    st_folium(m, width=None, height=450)

    st.markdown("**Kartenlegende:**")
    col_legend1, col_legend2 = st.columns(2)

    legend_items = [(cat, color) for cat, color in COLOR_MAPPING.items()]

    if result.get("workplace_lat") and result.get("workplace_lon"):
        legend_items.append(("workplace", "#FFA726"))

    for idx, (category, color) in enumerate(legend_items):
        if idx < 2:
            with col_legend1:
                st.markdown(
                    f"<span style='color: {color}; font-weight: bold;'>●</span> {CATEGORY_NAMES[category]}",
                    unsafe_allow_html=True,
                )
        else:
            with col_legend2:
                st.markdown(
                    f"<span style='color: {color}; font-weight: bold;'>●</span> {CATEGORY_NAMES[category]}",
                    unsafe_allow_html=True,
                )

    # Legende für gepinnte Suchradien
    if st.session_state.pinned_results:
        st.markdown("---")
        st.markdown("**📌 Gepinnte Suchradien:**")

        pinned_legend_col1, pinned_legend_col2 = st.columns(2)

        for idx, pinned in enumerate(st.session_state.pinned_results):
            radius_color = PINNED_RADIUS_COLORS[idx % len(PINNED_RADIUS_COLORS)]
            pinned_text = (
                f"{pinned['address']} ({format_radius(pinned.get('radius', 1500))})"
            )

            if idx < len(st.session_state.pinned_results) // 2 + 1:
                with pinned_legend_col1:
                    st.markdown(
                        f"<span style='color: {radius_color}; font-weight: bold;'>⬤</span> {pinned_text}",
                        unsafe_allow_html=True,
                    )
            else:
                with pinned_legend_col2:
                    st.markdown(
                        f"<span style='color: {radius_color}; font-weight: bold;'>⬤</span> {pinned_text}",
                        unsafe_allow_html=True,
                    )

    st.divider()

    st.subheader("📊 Kategorie-Übersicht")

    col_cat1, col_cat2 = st.columns(2)
    details = result["details"]

    for idx, detail in enumerate(details):
        category = detail["category"]
        color_class = get_score_color(detail["score"])
        emoji = score_to_emoji(detail["score"])
        category_name = CATEGORY_NAMES.get(category, category)
        weight = result.get("weights_applied", {}).get(category, 0)

        card_html = f"""
        <div class="metric-card {color_class}">
            <h4>{emoji} {category_name}</h4>
            <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">{detail["score"]}/100</p>
            <p style="font-size: 12px; color: #666; margin: 5px 0;">
                📍 {detail["nearest_po_dist"]:.0f}m entfernt
            </p>
            <p style="font-size: 12px; color: #666;">
                🔍 {detail["count_nearby"]} in der Nähe
            </p>
            <p style="font-size: 11px; color: #999;">
                Gewichtung: {weight:.1%}
            </p>
        </div>
        """

        if idx < 2:
            with col_cat1:
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            with col_cat2:
                st.markdown(card_html, unsafe_allow_html=True)

    st.divider()

    tab1, tab2 = st.tabs(["📋 Aktuelle Ergebnisse", "📌 Gepinnte Vergleiche"])

    with tab1:
        st.subheader("📋 Detaillierte Auswertung")

        df = pl.DataFrame(
            [
                {
                    "Kategorie": CATEGORY_NAMES[d["category"]]
                    .replace("🛒 ", "")
                    .replace("👨‍⚕️ ", "")
                    .replace("🚌 ", "")
                    .replace("🌳 ", "")
                    .replace("💼 ", ""),
                    "Punktzahl": f"{d['score']}/100",
                    "Nächstes Objekt (m)": f"{d['nearest_po_dist']:.0f}",
                    "In der Nähe": d["count_nearby"],
                    "Gewichtung": f"{result.get('weights_applied', {}).get(d['category'], 0):.1%}",
                }
                for d in result["details"]
            ]
        )

        st.dataframe(df, width="stretch", hide_index=True)

        st.divider()

        st.subheader("📥 Ergebnisse exportieren")
        col_exp1, col_exp2, col_exp3 = st.columns(3)

        with col_exp1:
            csv = df.write_csv()
            st.download_button(
                label="📥 CSV herunterladen",
                data=csv,
                file_name=f"wohnungsqualitaet-score_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

        with col_exp2:
            json_str = f"""{{
  "adresse": "{fixed_address}",
  "gesamtpunktzahl": {result["total_score"]},
  "koordinaten": {{"breite": {result["lat"]}, "länge": {result["lon"]}}},
  "zeitstempel": "{datetime.now().isoformat()}",
  "gewichtung": {str(result.get("weights_applied", {})).replace("'", '"')},
  "details": {str(result["details"]).replace("'", '"')}
}}"""
            st.download_button(
                label="📥 JSON herunterladen",
                data=json_str,
                file_name=f"wohnungsqualitaet-score_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

        with col_exp3:
            if st.button("📌 Ergebnis pinnen", width="stretch"):
                pinned_entry = {
                    "address": fixed_address,
                    "score": result["total_score"],
                    "lat": result["lat"],
                    "lon": result["lon"],
                    "radius": st.session_state.radius,  # Speichere den Suchradius
                    "timestamp": datetime.now().isoformat(),
                    "details": result["details"],
                    "weights_applied": result.get("weights_applied", {}),
                }
                st.session_state.pinned_results.append(pinned_entry)
                st.success(f"✅ Ergebnis für '{fixed_address}' gepinnt!")

    with tab2:
        st.subheader("📌 Gepinnte Vergleiche")

        if not st.session_state.pinned_results:
            st.info(
                "📍 Noch keine gepinnten Ergebnisse. "
                "Pinnen Sie Ergebnisse in der Registerkarte 'Aktuelle Ergebnisse', um sie hier zu vergleichen."
            )
        else:
            for idx, pinned in enumerate(st.session_state.pinned_results):
                col_pin1, col_pin2 = st.columns([3, 1])

                with col_pin1:
                    radius_display = (
                        f" | 📍 Radius: {format_radius(pinned.get('radius', 1500))}"
                        if "radius" in pinned
                        else ""
                    )
                    st.markdown(
                        f"**{pinned['address']}** - "
                        f"{score_to_emoji(pinned['score'])} {pinned['score']:.0f}/100{radius_display}"
                    )
                    st.caption(f"📅 {pinned['timestamp']}")

                with col_pin2:
                    if st.button("❌ Entfernen", key=f"remove_pinned_{idx}"):
                        st.session_state.pinned_results.pop(idx)
                        st.rerun()

                comparison_df = pl.DataFrame(
                    [
                        {
                            "Kategorie": CATEGORY_NAMES[d["category"]]
                            .replace("🛒 ", "")
                            .replace("👨‍⚕️ ", "")
                            .replace("🚌 ", "")
                            .replace("🌳 ", "")
                            .replace("💼 ", ""),
                            "Punktzahl": f"{d['score']}/100",
                            "Nächstes Objekt (m)": f"{d['nearest_po_dist']:.0f}",
                            "In der Nähe": d["count_nearby"],
                        }
                        for d in pinned["details"]
                    ]
                )
                st.dataframe(comparison_df, width="stretch", hide_index=True)
                st.divider()

    st.divider()

    if st.button("🔄 Ergebnisse löschen", width="stretch"):
        st.session_state.search_result = None
        st.session_state.last_address = None
        st.rerun()

elif address_input and not search_button:
    st.info('👆 Klicken Sie auf die Schaltfläche "Bewerten", um zu beginnen!')

else:
    st.markdown("""
    ### 🚀 Erste Schritte
    
    1. **Geben Sie eine Adresse ein** im Suchfeld oben
    2. **Klicken Sie auf \"Bewerten\"**, um die Nachbarschaft zu analysieren
    3. **Passen Sie die Gewichtung an** im linken Menü, um Ihre Vorlieben widerzuspiegeln
    4. **Sehen Sie die Ergebnisse** mit Gesamtbewertung und Kategorieaufschlüsselung
    5. **Erkunden Sie die Karte**, um die Lage und nahegelegene Einrichtungen zu sehen
    6. **Exportieren Sie Ergebnisse** in CSV oder JSON Format
    
    ---
    
    ### 📍 Wie es funktioniert
    
    Der Wohnungsqualität Score bewertet Nachbarschaften durch Berechnung der Entfernungen zu:
    - **Supermärkte** - Essential für den Lebensmitteleinkauf (anpassbare Gewichtung)
    - **Medizinische Einrichtungen** - Gesundheitszugang (anpassbare Gewichtung)
    - **Öffentliche Verkehrsmittel** - Mobilität und Pendeln (anpassbare Gewichtung)
    - **Parks** - Erholung und Grünflächen (anpassbare Gewichtung)
    
    Jede Kategorie erhält eine Punktzahl basierend auf der Nähe zur nächsten Einrichtung.
    Die Gewichtung können Sie anpassen, um den Gesamtscore nach Ihren persönlichen Vorlieben zu berechnen.
    """)
