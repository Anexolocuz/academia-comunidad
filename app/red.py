"""Conexiones HTTP(S) salientes que no se cuelgan cuando una dirección IPv6 no tiene ruta.

`urllib` prueba las direcciones en el orden en que las devuelve el sistema y con el tiempo de espera completo de cada
petición: si la primera es IPv6 y el equipo no tiene salida por IPv6, la petición espera todo ese tiempo (minutos) antes de
probar IPv4. Aquí se prueba IPv4 primero y la conexión tiene su propio límite corto; la espera larga de la lectura
(una respuesta de IA puede tardar) no cambia.
"""
import http.client
import socket
import urllib.request

CONEXION_S = 10


def ordenar(infos):
    """IPv4 antes que IPv6 (el orden entre direcciones de la misma familia se conserva)."""
    return sorted(infos, key=lambda i: i[0] != socket.AF_INET)


class _Https(http.client.HTTPSConnection):
    def connect(self):
        ultimo = None
        for fam, tipo, proto, _, dir_ in ordenar(socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)):
            s = socket.socket(fam, tipo, proto)
            try:
                s.settimeout(CONEXION_S)
                s.connect(dir_)
                s.settimeout(self.timeout if isinstance(self.timeout, (int, float)) else None)
                break
            except OSError as e:
                ultimo = e
                s.close()
        else:
            raise ultimo or OSError("sin direcciones")
        self.sock = self._context.wrap_socket(s, server_hostname=self.host)


class _Manejador(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Https, req, context=self._context)


_opener = urllib.request.build_opener(_Manejador())


def abrir(req, timeout=60):
    """Como `urllib.request.urlopen`, con IPv4 primero y límite de conexión corto."""
    return _opener.open(req, timeout=timeout)
