"""
Interactive UI for DLMM Compiler testing and visualization.
Run with: streamlit run ui.py
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os

# Import core modules
from templates import (
    generate_templates,
    approximate_nnls,
    create_target_distribution,
    create_gaussian_target,
    rectangle,
    curve,
    bid_ask
)
from input_handlers import (
    load_target_from_json,
    load_target_from_csv,
    validate_target_vector,
    normalize_target_vector,
    InputValidationError
)

st.set_page_config(
    page_title="DLMM Compiler",
    page_icon="📊",
    layout="wide"
)

st.title("DLMM Compiler - Strategy Optimizer")
st.markdown("Optimize liquidity distributions into Meteora DLMM strategies")

# Create tabs
tab1, tab2 = st.tabs(["📊 Optimizer", "✏️ Draw Distribution"])

# ============================================
# TAB 2: DRAW DISTRIBUTION (defined first so it can set session state)
# ============================================
with tab2:
    st.subheader("Draw Custom Distribution")
    st.markdown("Create a custom liquidity distribution by adjusting bin values")

    # Bin count selector
    draw_col1, draw_col2 = st.columns([1, 3])

    with draw_col1:
        draw_bins = st.slider("Number of Bins", min_value=10, max_value=100, value=25, key="draw_bins_slider")

        # Initialize or resize distribution in session state
        if "drawn_dist" not in st.session_state:
            st.session_state.drawn_dist = np.ones(draw_bins) / draw_bins
        elif len(st.session_state.drawn_dist) != draw_bins:
            # Resize: interpolate or reset
            old_dist = st.session_state.drawn_dist
            new_dist = np.interp(
                np.linspace(0, 1, draw_bins),
                np.linspace(0, 1, len(old_dist)),
                old_dist
            )
            st.session_state.drawn_dist = new_dist

        st.markdown("**Presets:**")

        if st.button("🔲 Flat", use_container_width=True):
            st.session_state.drawn_dist = np.ones(draw_bins) / draw_bins
            st.rerun()

        if st.button("⛰️ Peak Center", use_container_width=True):
            x = np.arange(draw_bins)
            center = draw_bins // 2
            sigma = draw_bins / 6
            st.session_state.drawn_dist = np.exp(-0.5 * ((x - center) / sigma) ** 2)
            st.rerun()

        if st.button("📈 Ramp Up", use_container_width=True):
            st.session_state.drawn_dist = np.linspace(0.1, 1.0, draw_bins)
            st.rerun()

        if st.button("🔔 Edges (U-shape)", use_container_width=True):
            x = np.arange(draw_bins)
            center = draw_bins // 2
            st.session_state.drawn_dist = np.abs(x - center) / center + 0.2
            st.rerun()

        if st.button("🎲 Random", use_container_width=True):
            st.session_state.drawn_dist = np.random.random(draw_bins) + 0.1
            st.rerun()

        if st.button("🗑️ Clear (zeros)", use_container_width=True):
            st.session_state.drawn_dist = np.zeros(draw_bins) + 0.01
            st.rerun()

    with draw_col2:
        # Live preview chart (above the editor)
        st.markdown("**Live Preview:**")

        current_dist = st.session_state.drawn_dist
        normalized_preview = current_dist / (np.sum(current_dist) + 1e-12)

        fig_preview = go.Figure()
        fig_preview.add_trace(go.Bar(
            x=list(range(draw_bins)),
            y=normalized_preview,
            marker_color='rgb(55, 126, 184)',
            name='Distribution'
        ))
        fig_preview.update_layout(
            xaxis_title="Bin",
            yaxis_title="Liquidity (normalized)",
            height=250,
            margin=dict(l=50, r=20, t=20, b=50),
            showlegend=False
        )
        st.plotly_chart(fig_preview, use_container_width=True)

        # Data editor for precise control
        st.markdown("**Edit Values:**")

        # Create editable dataframe
        edit_df = pd.DataFrame({
            "Bin": list(range(draw_bins)),
            "Value": st.session_state.drawn_dist.tolist()
        })

        edited_df = st.data_editor(
            edit_df,
            num_rows="fixed",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Bin": st.column_config.NumberColumn("Bin", disabled=True),
                "Value": st.column_config.NumberColumn(
                    "Value",
                    min_value=0.0,
                    max_value=10.0,
                    step=0.01,
                    format="%.3f"
                )
            },
            height=200
        )

        # Update session state from edited values
        st.session_state.drawn_dist = np.array(edited_df["Value"].tolist())

    st.divider()

    # Test and export buttons
    test_col1, test_col2, test_col3 = st.columns([2, 1, 1])

    with test_col1:
        max_strat_draw = st.number_input("Max Strategies", min_value=1, value=3, step=1, key="draw_max_strat")

    with test_col2:
        test_button = st.button("🚀 Test This Distribution", type="primary", use_container_width=True)

    with test_col3:
        # Export drawn distribution
        drawn_export = {
            "bins": (st.session_state.drawn_dist / (np.sum(st.session_state.drawn_dist) + 1e-12)).tolist(),
            "metadata": {"source": "drawn", "bin_count": draw_bins}
        }
        st.download_button(
            "📥 Export JSON",
            data=json.dumps(drawn_export, indent=2),
            file_name="drawn_distribution.json",
            mime="application/json",
            use_container_width=True
        )

    # Run optimization if test button clicked
    if test_button:
        with st.spinner("Running optimization..."):
            draw_target = st.session_state.drawn_dist.copy()
            draw_target = draw_target / (np.sum(draw_target) + 1e-12)

            # Generate templates and optimize
            draw_templates, draw_params = generate_templates(draw_bins)
            draw_result = approximate_nnls(
                draw_target, draw_templates, draw_params,
                max_strategies=max_strat_draw
            )

            st.session_state.draw_result = draw_result
            st.session_state.draw_target = draw_target

    # Show results if available
    if "draw_result" in st.session_state and "draw_target" in st.session_state:
        draw_result = st.session_state.draw_result
        draw_target = st.session_state.draw_target

        st.subheader("Optimization Results")

        # Metrics
        res_cols = st.columns(4)
        with res_cols[0]:
            st.metric("R² Score", f"{draw_result['r_squared']:.4f}")
        with res_cols[1]:
            st.metric("Residual", f"{draw_result['residual']:.6f}")
        with res_cols[2]:
            st.metric("Strategies", len(draw_result['strategies']))
        with res_cols[3]:
            if draw_result['truncated']:
                st.metric("R² Loss", f"{draw_result.get('r_squared_loss', 0):.4f}")
            else:
                st.metric("R² Loss", "N/A")

        # Comparison chart
        draw_approx = draw_result['approximation']
        B_draw = len(draw_target)

        fig_compare = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Target vs Approximation", "Strategy Breakdown")
        )

        fig_compare.add_trace(
            go.Scatter(x=list(range(B_draw)), y=draw_target,
                       mode='lines+markers', name='Target',
                       line=dict(color='blue', width=2)),
            row=1, col=1
        )
        fig_compare.add_trace(
            go.Scatter(x=list(range(B_draw)), y=draw_approx,
                       mode='lines+markers', name='Approximation',
                       line=dict(color='green', width=2, dash='dash')),
            row=1, col=1
        )

        # Strategy contributions
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        for i, (strat, weight) in enumerate(draw_result['strategies']):
            if strat['type'] == 'rectangle':
                strat_vec = rectangle(strat['center'], strat['width'], B_draw)
            elif strat['type'] == 'curve':
                strat_vec = curve(strat['center'], strat['width'], B_draw)
            elif strat['type'] == 'bid_ask':
                strat_vec = bid_ask(strat['center'], strat['width'], B_draw)

            strat_vec = strat_vec / (np.sum(strat_vec) + 1e-12) * weight

            fig_compare.add_trace(
                go.Bar(x=list(range(B_draw)), y=strat_vec,
                       name=f"{strat['type']} (w={weight:.2f})",
                       marker_color=colors[i % len(colors)]),
                row=1, col=2
            )

        fig_compare.update_layout(height=400, barmode='stack')
        st.plotly_chart(fig_compare, use_container_width=True)

        # Strategy table
        strat_data = []
        for i, (strat, weight) in enumerate(draw_result['strategies'], 1):
            strat_data.append({
                "#": i,
                "Type": strat['type'],
                "Center": strat['center'],
                "Width": strat['width'],
                "Weight": f"{weight:.4f}"
            })

        st.dataframe(pd.DataFrame(strat_data), use_container_width=True, hide_index=True)

        # Export strategy plan
        draw_plan = {
            "version": "1.0",
            "metrics": {
                "r_squared": float(draw_result["r_squared"]),
                "residual": float(draw_result["residual"])
            },
            "strategies": [
                {"type": s["type"], "center": s["center"], "width": s["width"], "weight": float(w)}
                for s, w in draw_result["strategies"]
            ]
        }
        st.download_button(
            "📥 Download Strategy Plan",
            data=json.dumps(draw_plan, indent=2),
            file_name="strategy_plan.json",
            mime="application/json"
        )


# ============================================
# TAB 1: OPTIMIZER (original functionality)
# ============================================
with tab1:
    # Sidebar for input configuration
    st.sidebar.header("Input Configuration")

    input_mode = st.sidebar.radio(
        "Target Source",
        ["Generate Distribution", "Load from JSON", "Load from CSV", "Manual Input"]
    )

    target = None
    B = 69
    metadata = {}

    if input_mode == "Generate Distribution":
        st.sidebar.subheader("Distribution Parameters")

        dist_type = st.sidebar.selectbox(
            "Distribution Type",
            ["gaussian", "uniform", "curve", "bid_ask"]
        )

        B = st.sidebar.slider("Number of Bins", min_value=10, max_value=200, value=69)
        center = st.sidebar.slider("Center Bin", min_value=0, max_value=B-1, value=B//2)

        if dist_type == "gaussian":
            sigma = st.sidebar.slider("Sigma (spread)", min_value=1.0, max_value=float(B//2), value=12.0)
            target = create_gaussian_target(B, center=center, sigma=sigma)
        else:
            width = st.sidebar.slider("Width", min_value=3, max_value=B, value=min(25, B))
            target = create_target_distribution(dist_type, B, center, 12.0, width)

        metadata = {"source": "generated", "type": dist_type}

    elif input_mode == "Load from JSON":
        uploaded_file = st.sidebar.file_uploader("Upload JSON file", type=["json"])

        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                if "bins" in data:
                    target = np.array(data["bins"], dtype=np.float64)
                    target = normalize_target_vector(target, method="sum")
                    B = len(target)
                    metadata = data.get("metadata", {})
                    metadata["source"] = "json_upload"
                    st.sidebar.success(f"Loaded {B} bins from JSON")
                else:
                    st.sidebar.error("JSON must contain 'bins' array")
            except Exception as e:
                st.sidebar.error(f"Error loading JSON: {e}")

        # Also allow selecting from existing files
        json_files = [f for f in os.listdir(".") if f.endswith(".json") and f != "plan.json"]
        if json_files:
            selected_file = st.sidebar.selectbox("Or select existing file", [""] + json_files)
            if selected_file:
                try:
                    target, metadata = load_target_from_json(selected_file)
                    B = len(target)
                    st.sidebar.success(f"Loaded {B} bins from {selected_file}")
                except Exception as e:
                    st.sidebar.error(f"Error: {e}")

    elif input_mode == "Load from CSV":
        uploaded_file = st.sidebar.file_uploader("Upload CSV file", type=["csv"])

        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.sidebar.write("Columns:", list(df.columns))

                col = st.sidebar.selectbox("Select liquidity column", df.columns)
                target = df[col].values.astype(np.float64)
                target = normalize_target_vector(target, method="sum")
                B = len(target)
                metadata = {"source": "csv_upload", "column": col}
                st.sidebar.success(f"Loaded {B} bins from CSV")
            except Exception as e:
                st.sidebar.error(f"Error loading CSV: {e}")

    elif input_mode == "Manual Input":
        st.sidebar.subheader("Enter values (comma-separated)")

        default_values = "0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.15, 0.1, 0.05, 0.02, 0.01"
        values_str = st.sidebar.text_area("Bin values", value=default_values)

        try:
            values = [float(x.strip()) for x in values_str.split(",") if x.strip()]
            target = np.array(values)
            target = normalize_target_vector(target, method="sum")
            B = len(target)
            metadata = {"source": "manual"}
            st.sidebar.success(f"Parsed {B} bins")
        except Exception as e:
            st.sidebar.error(f"Error parsing values: {e}")

    # Optimization parameters
    st.sidebar.header("Optimization")
    max_strategies = st.sidebar.number_input("Max Strategies", min_value=1, value=3, step=1)

    # Run optimization button
    run_optimization = st.sidebar.button("🚀 Run Optimization", type="primary")

    # Main content area
    if target is not None:
        # Validate target
        is_valid, error = validate_target_vector(target)

        if not is_valid:
            st.error(f"Invalid target vector: {error}")
        else:
            col1, col2 = st.columns([2, 1])

            with col1:
                st.subheader("Target Distribution")

                # Create target visualization
                fig_target = go.Figure()
                fig_target.add_trace(go.Bar(
                    x=list(range(B)),
                    y=target,
                    name="Target",
                    marker_color="rgb(55, 83, 109)"
                ))
                fig_target.update_layout(
                    xaxis_title="Bin",
                    yaxis_title="Liquidity (normalized)",
                    height=300,
                    margin=dict(l=50, r=50, t=30, b=50)
                )
                st.plotly_chart(fig_target, use_container_width=True)

            with col2:
                st.subheader("Target Stats")
                st.metric("Bins", B)
                st.metric("Peak Bin", int(np.argmax(target)))
                st.metric("Max Value", f"{np.max(target):.4f}")
                if metadata:
                    st.json(metadata)

            # Run optimization if requested or auto-run
            if run_optimization or "result" not in st.session_state:
                with st.spinner("Generating templates and optimizing..."):
                    # Generate templates
                    templates, params = generate_templates(B)

                    # Run optimization
                    result = approximate_nnls(
                        target, templates, params,
                        max_strategies=max_strategies
                    )

                    st.session_state.result = result
                    st.session_state.templates = templates
                    st.session_state.params = params

            if "result" in st.session_state:
                result = st.session_state.result

                st.divider()
                st.subheader("Optimization Results")

                # Metrics row
                met_cols = st.columns(4)
                with met_cols[0]:
                    st.metric("R² Score", f"{result['r_squared']:.4f}")
                with met_cols[1]:
                    st.metric("Residual", f"{result['residual']:.6f}")
                with met_cols[2]:
                    st.metric("Strategies", len(result['strategies']))
                with met_cols[3]:
                    if result['truncated']:
                        st.metric("R² Loss", f"{result.get('r_squared_loss', 0):.4f}")
                    else:
                        st.metric("R² Loss", "N/A")

                # Comparison chart
                st.subheader("Target vs Approximation")

                approximation = result['approximation']
                error = target - approximation

                fig = make_subplots(
                    rows=2, cols=2,
                    subplot_titles=(
                        "Overlay Comparison",
                        "Strategy Contributions",
                        "Approximation Error",
                        "Cumulative Distribution"
                    ),
                    row_heights=[0.6, 0.4]
                )

                # Overlay comparison
                fig.add_trace(
                    go.Scatter(
                        x=list(range(B)), y=target,
                        mode='lines+markers', name='Target',
                        line=dict(color='blue', width=2),
                        marker=dict(size=4)
                    ),
                    row=1, col=1
                )
                fig.add_trace(
                    go.Scatter(
                        x=list(range(B)), y=approximation,
                        mode='lines+markers', name='Approximation',
                        line=dict(color='green', width=2, dash='dash'),
                        marker=dict(size=4)
                    ),
                    row=1, col=1
                )

                # Strategy contributions (stacked bar)
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

                contributions = []
                for i, (strat, weight) in enumerate(result['strategies']):
                    if strat['type'] == 'rectangle':
                        strat_vec = rectangle(strat['center'], strat['width'], B)
                    elif strat['type'] == 'curve':
                        strat_vec = curve(strat['center'], strat['width'], B)
                    elif strat['type'] == 'bid_ask':
                        strat_vec = bid_ask(strat['center'], strat['width'], B)

                    strat_vec = strat_vec / (np.sum(strat_vec) + 1e-12)
                    contribution = strat_vec * weight
                    contributions.append(contribution)

                    fig.add_trace(
                        go.Bar(
                            x=list(range(B)), y=contribution,
                            name=f"{strat['type']} (c={strat['center']}, w={strat['width']})",
                            marker_color=colors[i % len(colors)]
                        ),
                        row=1, col=2
                    )

                fig.update_layout(barmode='stack')

                # Error plot
                fig.add_trace(
                    go.Bar(
                        x=list(range(B)), y=error,
                        name='Error',
                        marker_color=['red' if e < 0 else 'green' for e in error],
                        showlegend=False
                    ),
                    row=2, col=1
                )
                fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)

                # Cumulative distribution
                fig.add_trace(
                    go.Scatter(
                        x=list(range(B)), y=np.cumsum(target),
                        mode='lines', name='Target CDF',
                        line=dict(color='blue', width=2)
                    ),
                    row=2, col=2
                )
                fig.add_trace(
                    go.Scatter(
                        x=list(range(B)), y=np.cumsum(approximation),
                        mode='lines', name='Approx CDF',
                        line=dict(color='green', width=2, dash='dash')
                    ),
                    row=2, col=2
                )

                fig.update_layout(
                    height=700,
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )

                st.plotly_chart(fig, use_container_width=True)

                # Strategy details table
                st.subheader("Selected Strategies")

                strategy_data = []
                for i, (strat, weight) in enumerate(result['strategies'], 1):
                    strategy_data.append({
                        "#": i,
                        "Type": strat['type'],
                        "Center": strat['center'],
                        "Width": strat['width'],
                        "Weight": f"{weight:.4f}",
                        "Weight %": f"{weight * 100:.1f}%"
                    })

                st.dataframe(
                    pd.DataFrame(strategy_data),
                    use_container_width=True,
                    hide_index=True
                )

                # Export section
                st.subheader("Export")

                export_cols = st.columns(2)

                with export_cols[0]:
                    # Generate strategy plan JSON
                    plan = {
                        "version": "1.0",
                        "metrics": {
                            "r_squared": float(result["r_squared"]),
                            "residual": float(result["residual"]),
                            "truncated": result.get("truncated", False),
                            "full_r_squared": float(result.get("full_r_squared", result["r_squared"]))
                        },
                        "strategies": [
                            {
                                "type": strat["type"],
                                "center": int(strat["center"]),
                                "width": int(strat["width"]),
                                "weight": float(weight)
                            }
                            for strat, weight in result["strategies"]
                        ]
                    }

                    st.download_button(
                        label="📥 Download Strategy Plan (JSON)",
                        data=json.dumps(plan, indent=2),
                        file_name="strategy_plan.json",
                        mime="application/json"
                    )

                with export_cols[1]:
                    # Export target as JSON
                    target_export = {
                        "bins": target.tolist(),
                        "metadata": metadata
                    }

                    st.download_button(
                        label="📥 Download Target Distribution (JSON)",
                        data=json.dumps(target_export, indent=2),
                        file_name="target_distribution.json",
                        mime="application/json"
                    )

    else:
        st.info("Configure a target distribution in the sidebar to begin.")

        st.markdown("""
        ### Quick Start

        1. **Generate Distribution**: Create a synthetic target (Gaussian, uniform, etc.)
        2. **Load from JSON**: Upload a JSON file with `{"bins": [...]}` format
        3. **Load from CSV**: Upload a CSV with a liquidity column
        4. **Manual Input**: Enter comma-separated values directly

        ### JSON Format
        ```json
        {
          "bins": [0.01, 0.02, 0.15, 0.3, 0.15, 0.02, 0.01],
          "metadata": {
            "source": "market_data",
            "timestamp": "2026-01-27T00:00:00Z"
          }
        }
        ```
        """)


# Footer
st.divider()
st.caption("DLMM Compiler - Liquidity Distribution Optimizer")
