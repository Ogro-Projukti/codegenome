"""Tests for the Graph API abstraction."""

import networkx as nx

from codegenome.graph_api import IGraphGraph, NetworkXGraph, create_graph

def test_graph_api_parity():
    nx_graph = create_graph("networkx")
    ig_graph = create_graph("igraph")
    
    assert isinstance(nx_graph, NetworkXGraph)
    assert isinstance(ig_graph, IGraphGraph)
    
    for g in (nx_graph, ig_graph):
        g.add_node("A", type="file")
        g.add_node("B", type="file")
        g.add_edge("A", "B", weight=1.5)
        g.add_edge("B", "A", weight=2.0)
        g.add_node("C", type="file")
        g.add_edge("B", "C", weight=3.0)
        
    assert nx_graph.number_of_nodes() == ig_graph.number_of_nodes() == 3
    assert nx_graph.number_of_edges() == ig_graph.number_of_edges() == 3
    
    assert nx_graph.has_node("A") == ig_graph.has_node("A")
    assert not nx_graph.has_node("D")
    assert not ig_graph.has_node("D")
    
    assert nx_graph.get_node("A") == ig_graph.get_node("A") == {"type": "file"}
    assert nx_graph.get_edge("A", "B") == ig_graph.get_edge("A", "B") == {"weight": 1.5}
    
    nx_nodes = {n: d for n, d in nx_graph.iter_nodes()}
    ig_nodes = {n: d for n, d in ig_graph.iter_nodes()}
    assert nx_nodes == ig_nodes
    
    nx_edges = {(s, t): d for s, t, d in nx_graph.iter_edges()}
    ig_edges = {(s, t): d for s, t, d in ig_graph.iter_edges()}
    assert nx_edges == ig_edges
    
    nx_in_b = {(s, t): d for s, t, d in nx_graph.in_edges("B")}
    ig_in_b = {(s, t): d for s, t, d in ig_graph.in_edges("B")}
    assert nx_in_b == ig_in_b == {("A", "B"): {"weight": 1.5}}
    
    nx_out_b = {(s, t): d for s, t, d in nx_graph.out_edges("B")}
    ig_out_b = {(s, t): d for s, t, d in ig_graph.out_edges("B")}
    assert nx_out_b == ig_out_b == {("B", "A"): {"weight": 2.0}, ("B", "C"): {"weight": 3.0}}
    
    assert set(nx_graph.neighbors("B")) == set(ig_graph.neighbors("B")) == {"A", "C"}
    
    nx_scc = {frozenset(c) for c in nx_graph.strongly_connected_components()}
    ig_scc = {frozenset(c) for c in ig_graph.strongly_connected_components()}
    assert nx_scc == ig_scc == {frozenset(["A", "B"]), frozenset(["C"])}
    
    # Test removal
    nx_graph.remove_nodes_from(["C"])
    ig_graph.remove_nodes_from(["C"])
    
    assert nx_graph.number_of_nodes() == ig_graph.number_of_nodes() == 2
    assert nx_graph.number_of_edges() == ig_graph.number_of_edges() == 2
    
    assert not nx_graph.has_node("C")
    assert not ig_graph.has_node("C")
    
    # Test attribute setting
    nx_graph.set_node_attr("A", "seen", True)
    ig_graph.set_node_attr("A", "seen", True)
    assert nx_graph.get_node("A") == ig_graph.get_node("A") == {"type": "file", "seen": True}

def test_igraph_to_networkx_conversion():
    ig_graph = create_graph("igraph")
    ig_graph.add_node("A", val=1)
    ig_graph.add_node("B", val=2)
    ig_graph.add_edge("A", "B", weight=5)
    
    nx_g = ig_graph.to_networkx()
    assert isinstance(nx_g, nx.DiGraph)
    assert nx_g.number_of_nodes() == 2
    assert nx_g.number_of_edges() == 1
    assert nx_g.nodes["A"] == {"val": 1}
    assert nx_g.edges["A", "B"] == {"weight": 5}
