from flask import Blueprint, request, jsonify
from app.services.serp_search import ScholarSearcher

api = Blueprint('api', __name__)

@api.route('/citations/<paper_id>')
def get_citations(paper_id):
    try:
        searcher = ScholarSearcher()
        network = searcher.get_citation_network(paper_id)
        return jsonify(network)
    except Exception as e:
        return jsonify({'error': str(e)}), 500