#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock
import json

from src.app import fetch_telemetry_data, classify_errors, apply_auto_healing

class TestApp(unittest.TestCase):
    
    def test_fetch_telemetry_data_default(self):
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": []}
            mock_get.return_value = mock_response
            
            result = fetch_telemetry_data()
            self.assertEqual(result, {"data": []})
            mock_get.assert_called_once_with("http://localhost:8000/telemetry", params={"minutes": 30})
    
    def test_fetch_telemetry_data_custom(self):
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": []}
            mock_get.return_value = mock_response
            
            result = fetch_telemetry_data(unit="nginx", minutes=60)
            self.assertEqual(result, {"data": []})
            mock_get.assert_called_once_with("http://localhost:8000/telemetry", params={"unit": "nginx", "minutes": 60})
    
    def test_classify_errors(self):
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"classified_errors": []}
            mock_post.return_value = mock_response
            
            result = classify_errors({})
            self.assertEqual(result, {"classified_errors": []})
            mock_post.assert_called_once_with("http://localhost:8000/classify", json={})
    
    def test_apply_auto_healing(self):
        classified_errors = {
            "errors": [
                {"signature": "Error1", "severity": "critical"},
                {"signature": "Error2", "severity": "warning"}
            ]
        }
        apply_auto_healing(classified_errors)
        # Placeholder for actual assert logic
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
