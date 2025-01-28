from typing import List, Dict, Any, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

class DataVisualizer:
    """Utility class for creating visualizations"""
    
    @staticmethod
    def create_price_chart(
        data: List[Dict[str, Any]],
        title: str = "Price Chart"
    ) -> Dict[str, Any]:
        """Create price/time series chart"""
        df = pd.DataFrame(data)
        
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='lines',
                name='Price'
            )
        )
        
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Price",
            template="plotly_dark"
        )
        
        return fig.to_dict()

    @staticmethod
    def create_token_distribution(
        holdings: Dict[str, float],
        title: str = "Token Distribution"
    ) -> Dict[str, Any]:
        """Create token distribution pie chart"""
        labels = list(holdings.keys())
        values = list(holdings.values())
        
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=.3
                )
            ]
        )
        
        fig.update_layout(
            title=title,
            template="plotly_dark"
        )
        
        return fig.to_dict()

    @staticmethod
    def create_tvl_chart(
        data: List[Dict[str, Any]],
        protocols: Optional[List[str]] = None,
        title: str = "TVL Chart"
    ) -> Dict[str, Any]:
        """Create TVL comparison chart"""
        df = pd.DataFrame(data)
        
        fig = go.Figure()
        
        if protocols:
            for protocol in protocols:
                fig.add_trace(
                    go.Scatter(
                        x=df['timestamp'],
                        y=df[protocol],
                        mode='lines',
                        name=protocol
                    )
                )
        else:
            fig.add_trace(
                go.Scatter(
                    x=df['timestamp'],
                    y=df['tvl'],
                    mode='lines',
                    name='TVL'
                )
            )
        
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="TVL",
            template="plotly_dark"
        )
        
        return fig.to_dict()

    @staticmethod
    def create_network_graph(
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        title: str = "Network Graph"
    ) -> Dict[str, Any]:
        """Create network visualization"""
        node_trace = go.Scatter(
            x=[node['x'] for node in nodes],
            y=[node['y'] for node in nodes],
            mode='markers+text',
            text=[node['label'] for node in nodes],
            marker=dict(
                size=10,
                color=[node.get('color', '#888') for node in nodes]
            )
        )
        
        edge_trace = go.Scatter(
            x=[item for edge in edges for item in [edge['source_x'], edge['target_x'], None]],
            y=[item for edge in edges for item in [edge['source_y'], edge['target_y'], None]],
            mode='lines',
            line=dict(width=0.5, color='#888')
        )
        
        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title=title,
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20,l=5,r=5,t=40),
                template="plotly_dark"
            )
        )
        
        return fig.to_dict()

    @staticmethod
    def create_volume_analysis(
        data: List[Dict[str, Any]],
        title: str = "Volume Analysis"
    ) -> Dict[str, Any]:
        """Create volume analysis chart with price overlay"""
        df = pd.DataFrame(data)
        
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=(title, 'Volume')
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='lines',
                name='Price'
            ),
            row=1,
            col=1
        )
        
        fig.add_trace(
            go.Bar(
                x=df['timestamp'],
                y=df['volume'],
                name='Volume'
            ),
            row=2,
            col=1
        )
        
        fig.update_layout(
            template="plotly_dark",
            height=600
        )
        
        return fig.to_dict()

    @staticmethod
    def create_heatmap(
        data: List[List[float]],
        x_labels: List[str],
        y_labels: List[str],
        title: str = "Heatmap"
    ) -> Dict[str, Any]:
        """Create heatmap visualization"""
        fig = go.Figure(
            data=go.Heatmap(
                z=data,
                x=x_labels,
                y=y_labels,
                colorscale='Viridis'
            )
        )
        
        fig.update_layout(
            title=title,
            template="plotly_dark"
        )
        
        return fig.to_dict()
