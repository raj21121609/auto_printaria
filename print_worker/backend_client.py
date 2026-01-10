import requests
import json
import logging

class BackendClient:
    def __init__(self, backend_url, auth_token):
        self.backend_url = backend_url.rstrip('/')
        self.auth_token = auth_token
        self.headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Content-Type': 'application/json'
        }

    def get_pending_jobs(self, shop_id):
        """
        Poll the backend for print jobs with payment_status='PAID' and print_status='PENDING' for the given shop_id.
        Returns a list of job dictionaries or None if failed.
        """
        try:
            url = f"{self.backend_url}/api/orders"
            params = {
                'shop_id': shop_id,
                'payment_status': 'PAID',
                'print_status': 'PENDING'
            }
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            jobs = response.json()
            return jobs if isinstance(jobs, list) else []
        except requests.RequestException as e:
            logging.error(f"Failed to fetch pending jobs: {e}")
            return None

    def update_job_status(self, job_id, status):
        """
        Update the print_status of a job to the given status.
        Returns True if successful, False otherwise.
        """
        try:
            url = f"{self.backend_url}/api/orders/{job_id}"
            data = {'print_status': status}
            response = requests.put(url, headers=self.headers, json=data, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logging.error(f"Failed to update job {job_id} status to {status}: {e}")
            return False