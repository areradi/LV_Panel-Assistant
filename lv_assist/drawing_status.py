from functools import wraps


def preliminary_drawing(render):
    @wraps(render)
    def wrapped(*args, **kwargs):
        svg = render(*args, **kwargs)
        stamp = ('<text x="98%" y="98%" text-anchor="end" font-size="11" '
                 'fill="#805000">PRELIMINARY: engineering review required</text>')
        return svg.replace('</svg>', stamp + '</svg>')
    return wrapped
