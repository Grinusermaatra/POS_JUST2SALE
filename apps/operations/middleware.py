class RegisterLockMiddleware:
    """El bloqueo de la pantalla de caja se completa en la etapa de operación."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
