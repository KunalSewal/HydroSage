// Text for the always-visible label on the pond marker. The brief requires
// the pond location, catchment area and expected water volume to be shown
// *on the map*, not only in the results sheet. One combined label rather
// than one per layer: separate pond and catchment labels overlapped, since
// the pond sits inside its catchment.
export function pondLabel(
  runoffVolumeM3: number | null | undefined,
  catchmentHectares: number | null | undefined,
): string {
  const lines = ['Pond site']
  if (runoffVolumeM3 !== null && runoffVolumeM3 !== undefined) {
    lines.push(`~${Math.round(runoffVolumeM3).toLocaleString('en-US')} m³ water/yr`)
  }
  if (catchmentHectares !== null && catchmentHectares !== undefined) {
    lines.push(`Catchment ${catchmentHectares.toFixed(1)} ha`)
  }
  return lines.join('\n')
}
