def csv_to_eeFeat(df, proj, wrs):
  """Function to create an eeFeature from the location info

  Args:
      df: point locations .csv file with Latitude and Longitude
      proj: CRS projection of the points
      wrs: current tile

  Returns:
      ee.FeatureCollection of the points 
  """
  features=[]
  for i in (df.index):
    x,y = df.Longitude[i],df.Latitude[i]
    latlong =[x,y]
    loc_properties = {"system:index": str(df.id[i]), 
    "id": str(df.id[i]),
    "wrs": str(wrs)}
    g=ee.Geometry.Point(latlong, proj) 
    feature = ee.Feature(g, loc_properties)
    features.append(feature)
  ee_object = ee.FeatureCollection(features)
  return ee_object


def apply_scale_factors(image):
  """ Applies scaling factors for Landsat Collection 2 surface reflectance 
  and surface temperature products

  Args:
      image: one ee.Image of an ee.ImageCollection

  Returns:
      ee.Image with band values overwritten by scaling factors
  """
  opticalBands = image.select("SR_B.").multiply(0.0000275).add(-0.2)
  thermalBands = image.select("ST_B.*").multiply(0.00341802).add(149.0)
  return image.addBands(opticalBands, None, True).addBands(thermalBands, None,True)


def dp_buff(feature):
  """ Buffer ee.FeatureCollection sites from csv_to_eeFeat by user-specified radius

  Args:
      feature: ee.Feature of an ee.FeatureCollection

  Returns:
      ee.FeatureCollection of polygons resulting from buffered points
  """
  return feature.buffer(ee.Number.parse(str(buffer)))


def add_rad_mask(image):
  """Mask out all pixels that are radiometrically saturated using the QA_RADSAT
  QA band.

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      ee.Image with additional band called "radsat", where pixels with a value 
      of 0 are saturated for at least one SR band and a value of 1 is not saturated
  """
  #grab the radsat band
  satQA = image.select("radsat_qa")
  # all must be non-saturated per pixel
  satMask = satQA.eq(0).rename("radsat")
  return image.addBands(satMask)


def cf_mask(image):
  """Masks any pixels obstructed by clouds and snow/ice

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      ee.Image with additional band called "cfmask", where pixels are given values
      based on the QA_PIXEL band informaiton. Generally speaking, 0 is clear, values 
      greater than 0 are obstructed by clouds and/or snow/ice
  """
  #grab just the pixel_qa info
  qa = image.select("pixel_qa")
  cloudqa = (qa.bitwiseAnd(1 << 1).rename("cfmask") #dialated clouds value 1
    .where(qa.bitwiseAnd(1 << 3), ee.Image(2)) # clouds value 2
    .where(qa.bitwiseAnd(1 << 4), ee.Image(3)) # cloud shadows value 3
    .where(qa.bitwiseAnd(1 << 5), ee.Image(4))) # snow value 4
  return image.addBands(cloudqa)


def sr_cloud_mask(image):
  """Masks any pixles in Landsat 4-7 that are contaminated by the inputs of 
  the atmospheric processing steps

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      ee.Image with additional band called "sr_cloud", where pixels are given values
      based on the SR_CLOUD_QA band informaiton. Generally speaking, 0 is clear, values
      greater than 0 are obstructed by clouds and/or snow/ice specifically from atmospheric
      processing steps
  """
  srCloudQA = image.select("cloud_qa")
  srMask = (srCloudQA.bitwiseAnd(1 << 1).rename("sr_cloud") # cloud
    .where(srCloudQA.bitwiseAnd(1 << 2), ee.Image(2)) # cloud shadow
    .where(srCloudQA.bitwiseAnd(1 << 3), ee.Image(3)) # adjacent to cloud
    .where(srCloudQA.bitwiseAnd(1 << 4), ee.Image(4))) # snow/ice
  return image.addBands(srMask)


def sr_aerosol(image):
  """Flags any pixels in Landsat 8 and 9 that have "medium" or "high" aerosol QA flags from the
  SR_QA_AEROSOL band.

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      ee.Image with additional band called "medHighAero", where pixels are given a value of 1
      if the aerosol QA flag is medium or high and 0 otherwise
  """
  aerosolQA = image.select("aerosol_qa")
  medHighAero = aerosolQA.bitwiseAnd(1 << 7).rename("medHighAero")# pull out mask out where aeorosol is med and high
  return image.addBands(medHighAero)


def Mndwi(image):
  """calculate the modified normalized difference water index per pixel

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      band where values calculated are the MNDWI value per pixel
  """
  return (image.expression("(GREEN - SWIR1) / (GREEN + SWIR1)", {
    "GREEN": image.select(["Green"]),
    "SWIR1": image.select(["Swir1"])
  }).rename("mndwi"))
  

def Mbsrv(image):
  """calculate the multi-band spectral relationship visible per pixel

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      band where values calculated are the MBSRV value per pixel
  """
  return (image.select(["Green"]).add(image.select(["Red"])).rename("mbsrv"))


def Mbsrn(image):
  """calculate the multi-band spectral relationship near infrared per pixel

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      band where values calculated are the MBSRN value per pixel
  """
  return (image.select(["Nir"]).add(image.select(["Swir1"])).rename("mbsrn"))


def Ndvi(image):
  """calculate the normalized difference vegetation index per pixel

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      band where values calculated are the NDVI value per pixel
  """
  return (image.expression("(NIR - RED) / (NIR + RED)", {
    "RED": image.select(["Red"]),
    "NIR": image.select(["Nir"])
  }).rename("ndvi"))


def Awesh(image):
  """calculate the automated water extent shadow per pixel

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      band where values calculated are the AWESH value per pixel
  """
  return (image.expression("Blue + 2.5 * Green + (-1.5) * mbsrn + (-0.25) * Swir2", {
    "Blue": image.select(["Blue"]),
    "Green": image.select(["Green"]),
    "mbsrn": Mbsrn(image).select(["mbsrn"]),
    "Swir2": image.select(["Swir2"])
  }).rename("awesh"))


## The DSWE Function itself    
def DSWE(image):
  """calculate the dynamic surface water extent per pixel
  
  Args:
      image: ee.Image of an ee.ImageCollection
      
  Returns:
      band where values calculated are the DSWE value per pixel
  """
  mndwi = Mndwi(image)
  mbsrv = Mbsrv(image)
  mbsrn = Mbsrn(image)
  awesh = Awesh(image)
  swir1 = image.select(["Swir1"])
  nir = image.select(["Nir"])
  ndvi = Ndvi(image)
  blue = image.select(["Blue"])
  swir2 = image.select(["Swir2"])
  # These thresholds are taken from the LS Collection 2 DSWE Data Format Control Book
  # Inputs are meant to be scaled reflectance values 
  t1 = mndwi.gt(0.124) # MNDWI greater than Wetness Index Threshold
  t2 = mbsrv.gt(mbsrn) # MBSRV greater than MBSRN
  t3 = awesh.gt(0) #AWESH greater than 0
  t4 = (mndwi.gt(-0.44)  #Partial Surface Water 1 thresholds
   .And(swir1.lt(0.09)) #900 for no scaling (LS Collection 1)
   .And(nir.lt(0.15)) #1500 for no scaling (LS Collection 1)
   .And(ndvi.lt(0.7)))
  t5 = (mndwi.gt(-0.5) #Partial Surface Water 2 thresholds
   .And(blue.lt(0.1)) #1000 for no scaling (LS Collection 1)
   .And(swir1.lt(0.3)) #3000 for no scaling (LS Collection 1)
   .And(swir2.lt(0.1)) #1000 for no scaling (LS Collection 1)
   .And(nir.lt(0.25))) #2500 for no scaling (LS Collection 1)
  t = (t1
    .add(t2.multiply(10))
    .add(t3.multiply(100))
    .add(t4.multiply(1000))
    .add(t5.multiply(10000)))
  noWater = (t.eq(0)
    .Or(t.eq(1))
    .Or(t.eq(10))
    .Or(t.eq(100))
    .Or(t.eq(1000)))
  hWater = (t.eq(1111)
    .Or(t.eq(10111))
    .Or(t.eq(11011))
    .Or(t.eq(11101))
    .Or(t.eq(11110))
    .Or(t.eq(11111)))
  mWater = (t.eq(111)
    .Or(t.eq(1011))
    .Or(t.eq(1101))
    .Or(t.eq(1110))
    .Or(t.eq(10011))
    .Or(t.eq(10101))
    .Or(t.eq(10110))
    .Or(t.eq(11001))
    .Or(t.eq(11010))
    .Or(t.eq(11100)))
  pWetland = t.eq(11000)
  lWater = (t.eq(11)
    .Or(t.eq(101))
    .Or(t.eq(110))
    .Or(t.eq(1001))
    .Or(t.eq(1010))
    .Or(t.eq(1100))
    .Or(t.eq(10000))
    .Or(t.eq(10001))
    .Or(t.eq(10010))
    .Or(t.eq(10100)))
  iDswe = (noWater.multiply(0)
    .add(hWater.multiply(1))
    .add(mWater.multiply(2))
    .add(pWetland.multiply(3))
    .add(lWater.multiply(4)))
  return iDswe.rename("dswe")


def calc_hill_shades(image, geo):
  """ caluclate the hill shade per pixel

  Args:
      image: ee.Image of an ee.ImageCollection
      geo: geometry of the feature as feat.geometry() in script

  Returns:
      a band named "hillShade" where values calculated are the hill shade per 
      pixel. output is 0-255. 
  """
  MergedDEM = ee.Image("MERIT/DEM/v1_0_3").clip(geo.buffer(3000));
  hillShade = ee.Terrain.hillshade(MergedDEM, 
    ee.Number(image.get("SUN_AZIMUTH")), 
    ee.Number(image.get("SUN_ELEVATION")))
  hillShade = hillShade.rename(["hillShade"])
  return hillShade


def calc_hill_shadows(image, geo):
  """ caluclate the hill shadow per pixel
  
  Args:
      image: ee.Image of an ee.ImageCollection
      geo: geometry of the feature tile as feat.geometry() in script
  
  Returns:
      a band named "hillShadow" where values calculated are the hill shadow per 
      pixel. output 1 where pixels are illumunated and 0 where they are shadowed.
  """
  MergedDEM = ee.Image("MERIT/DEM/v1_0_3").clip(geo.buffer(3000));
  hillShadow = ee.Terrain.hillShadow(MergedDEM, 
    ee.Number(image.get("SUN_AZIMUTH")),
    ee.Number(90).subtract(image.get("SUN_ELEVATION")), 
    30)
  hillShadow = hillShadow.rename(["hillShadow"])
  return hillShadow


## Remove geometries
def remove_geo(image):
  """ Funciton to remove the geometry from an ee.Image
  
  Args:
      image: ee.Image of an ee.ImageCollection
      
  Returns:
      ee.Image with the geometry removed
  """
  return image.setGeometry(None)


## Set up the reflectance pull
def ref_pull_457_DSWE1(image):
  """ This function applies all functions to the Landsat 4-7 ee.ImageCollection, extracting
  summary statistics for each geometry area where the DSWE value is 1 (high confidence water)

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      summaries for band data within any given geometry area where the DSWE value is 1
  """
  # process image with the radsat mask
  r = add_rad_mask(image).select("radsat")
  # process image with cfmask
  f = cf_mask(image).select("cfmask")
  # process image with SR cloud mask
  s = sr_cloud_mask(image).select("sr_cloud")
  # where the f mask is > 2 (clouds and cloud shadow), call that 1 (otherwise 0) and rename as clouds.
  clouds = f.gte(1).rename("clouds")
  #apply dswe function
  d = DSWE(image).select("dswe")
  pCount = d.gt(0).rename("dswe_gt0").updateMask(f.eq(0)).updateMask(r.eq(1)).updateMask(s.eq(0)).selfMask()
  dswe1 = d.eq(1).rename("dswe1").updateMask(f.eq(0)).updateMask(r.eq(1)).updateMask(s.eq(0)).selfMask()
  # band where dswe is 3 and apply all masks
  dswe3 = d.eq(3).rename("dswe3").updateMask(f.eq(0)).updateMask(r.eq(1)).updateMask(s.eq(0)).selfMask()
  #calculate hillshade
  h = calc_hill_shades(image, feat.geometry()).select("hillShade")
  #calculate hillshadow
  hs = calc_hill_shadows(image, feat.geometry()).select("hillShadow")
  img_mask = (d.eq(1) # only high confidence water
            .updateMask(r.eq(1)) #1 == no saturated pixels
            .updateMask(f.eq(0)) #no snow or clouds
            .updateMask(s.eq(0)) # no SR processing artefacts
            .updateMask(hs.eq(1)) # only illuminated pixels
            .selfMask())
  pixOut = (image.select(["Blue", "Green", "Red", "Nir", "Swir1", "Swir2", 
                        "SurfaceTemp", "temp_qa", "ST_ATRAN", "ST_DRAD", "ST_EMIS",
                        "ST_EMSD", "ST_TRAD", "ST_URAD"],
                        ["med_Blue", "med_Green", "med_Red", "med_Nir", "med_Swir1", "med_Swir2", 
                        "med_SurfaceTemp", "med_temp_qa", "med_atran", "med_drad", "med_emis",
                        "med_emsd", "med_trad", "med_urad"])
            .addBands(image.select(["SurfaceTemp", "ST_CDIST"],
                                    ["min_SurfaceTemp", "min_cloud_dist"]))
            .addBands(image.select(["Blue", "Green", "Red", 
                                    "Nir", "Swir1", "Swir2", "SurfaceTemp"],
                                  ["sd_Blue", "sd_Green", "sd_Red", 
                                  "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"]))
            .addBands(image.select(["Blue", "Green", "Red", "Nir", 
                                    "Swir1", "Swir2", 
                                    "SurfaceTemp"],
                                  ["mean_Blue", "mean_Green", "mean_Red", "mean_Nir", 
                                  "mean_Swir1", "mean_Swir2", 
                                  "mean_SurfaceTemp"]))
            .addBands(image.select(["SurfaceTemp"]))
            .updateMask(img_mask.eq(1))
            # add these bands back in to create summary statistics without the influence of the DSWE masks:
            .addBands(pCount) 
            .addBands(dswe1)
            .addBands(dswe3)
            .addBands(clouds) 
            .addBands(hs)
            .addBands(h)
            ) 
  combinedReducer = (ee.Reducer.median().unweighted().forEachBand(pixOut.select(["med_Blue", "med_Green", "med_Red", 
            "med_Nir", "med_Swir1", "med_Swir2", "med_SurfaceTemp", 
            "med_temp_qa","med_atran", "med_drad", "med_emis",
            "med_emsd", "med_trad", "med_urad"]))
    .combine(ee.Reducer.min().unweighted().forEachBand(pixOut.select(["min_SurfaceTemp", "min_cloud_dist"])), sharedInputs = False)
    .combine(ee.Reducer.stdDev().unweighted().forEachBand(pixOut.select(["sd_Blue", "sd_Green", "sd_Red", "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["mean_Blue", "mean_Green", "mean_Red", 
              "mean_Nir", "mean_Swir1", "mean_Swir2", "mean_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.kurtosis().unweighted().forEachBand(pixOut.select(["SurfaceTemp"])), outputPrefix = "kurt_", sharedInputs = False)
    .combine(ee.Reducer.count().unweighted().forEachBand(pixOut.select(["dswe_gt0", "dswe1", "dswe3"])), outputPrefix = "pCount_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["clouds", "hillShadow"])), outputPrefix = "prop_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["hillShade"])), outputPrefix = "mean_", sharedInputs = False)
    )
  # apply combinedReducer to the image collection, mapping over each feature
  lsout = (pixOut.reduceRegions(feat, combinedReducer, 30))
  out = lsout.map(remove_geo)
  return out

def ref_pull_457_DSWE3(image):
  """ This function applies all functions to the Landsat 4-7 ee.ImageCollection, extracting
  summary statistics for each geometry area where the DSWE value is 3 (high confidence
  vegetated pixel)

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      summaries for band data within any given geometry area where the DSWE value is 3
  """
  # process image with the radsat mask
  r = add_rad_mask(image).select("radsat")
  # process image with cfmask
  f = cf_mask(image).select("cfmask")
  # process image with st SR cloud mask
  s = sr_cloud_mask(image).select("sr_cloud")
  # where the f mask is >= 1 (clouds and cloud shadow), call that 1 (otherwise 0) and rename as clouds.
  clouds = f.gte(1).rename("clouds")
  #apply dswe function
  d = DSWE(image).select("dswe")
  pCount = d.gt(0).rename("dswe_gt0").updateMask(f.eq(0)).updateMask(r.eq(1)).updateMask(s.eq(0)).selfMask()
  dswe1 = d.eq(1).rename("dswe1").updateMask(f.eq(0)).updateMask(r.eq(1)).updateMask(s.eq(0)).selfMask()
  # band where dswe is 3 and apply all masks
  dswe3 = d.eq(3).rename("dswe3").updateMask(f.eq(0)).updateMask(r.eq(1)).updateMask(s.eq(0)).selfMask()
  #calculate hillshade
  h = calc_hill_shades(image, feat.geometry()).select("hillShade")
  #calculate hillshadow
  hs = calc_hill_shadows(image, feat.geometry()).select("hillShadow")
  img_maks = (d.eq(3) # only vegetated water
          .updateMask(r.eq(1)) #1 == no saturated pixels
          .updateMask(f.eq(0)) #no snow or clouds
          .updateMask(s.eq(0)) # no SR processing artefacts
          .updateMask(hs.eq(1)) # only illuminated pixels
          .selfMask())
  pixOut = (image.select(["Blue", "Green", "Red", "Nir", "Swir1", "Swir2", 
                      "SurfaceTemp", "temp_qa", "ST_ATRAN", "ST_DRAD", "ST_EMIS",
                      "ST_EMSD", "ST_TRAD", "ST_URAD"],
                      ["med_Blue", "med_Green", "med_Red", "med_Nir", "med_Swir1", "med_Swir2", 
                      "med_SurfaceTemp", "med_temp_qa", "med_atran", "med_drad", "med_emis",
                      "med_emsd", "med_trad", "med_urad"])
          .addBands(image.select(["SurfaceTemp", "ST_CDIST"],
                                  ["min_SurfaceTemp", "min_cloud_dist"]))
          .addBands(image.select(["Blue", "Green", "Red", 
                                  "Nir", "Swir1", "Swir2", "SurfaceTemp"],
                                ["sd_Blue", "sd_Green", "sd_Red", 
                                "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"]))
          .addBands(image.select(["Blue", "Green", "Red", "Nir", 
                                    "Swir1", "Swir2", 
                                    "SurfaceTemp"],
                                  ["mean_Blue", "mean_Green", "mean_Red", "mean_Nir", 
                                  "mean_Swir1", "mean_Swir2", 
                                  "mean_SurfaceTemp"]))
          .addBands(image.select(["SurfaceTemp"]))
          .updateMask(img_mask.eq(1))
          # add these bands back in to create summary statistics without the influence of the DSWE masks:
          .addBands(pCount) 
          .addBands(dswe1)
          .addBands(dswe3)
          .addBands(clouds) 
          .addBands(hs)
          .addBands(h)
          ) 
  combinedReducer = (ee.Reducer.median().unweighted().forEachBand(pixOut.select(["med_Blue", "med_Green", "med_Red", 
            "med_Nir", "med_Swir1", "med_Swir2", "med_SurfaceTemp", 
            "med_temp_qa","med_atran", "med_drad", "med_emis",
            "med_emsd", "med_trad", "med_urad"]))
    .combine(ee.Reducer.min().unweighted().forEachBand(pixOut.select(["min_SurfaceTemp", "min_cloud_dist"])), sharedInputs = False)
    .combine(ee.Reducer.stdDev().unweighted().forEachBand(pixOut.select(["sd_Blue", "sd_Green", "sd_Red", "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["mean_Blue", "mean_Green", "mean_Red", 
              "mean_Nir", "mean_Swir1", "mean_Swir2", "mean_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.kurtosis().unweighted().forEachBand(pixOut.select(["SurfaceTemp"])), outputPrefix = "kurt_", sharedInputs = False)
    .combine(ee.Reducer.count().unweighted().forEachBand(pixOut.select(["dswe_gt0", "dswe1", "dswe3"])), outputPrefix = "pCount_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["clouds", "hillShadow"])), outputPrefix = "prop_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["hillShade"])), outputPrefix = "mean_", sharedInputs = False)
    )
  # apply combinedReducer to the image collection, mapping over each feature
  lsout = (pixOut.reduceRegions(feat, combinedReducer, 30))
  out = lsout.map(remove_geo)
  return out


def ref_pull_89_DSWE1(image):
  """ This function applies all functions to the Landsat 8 and 9 ee.ImageCollection, extracting
  summary statistics for each geometry area where the DSWE value is 1 (high confidence water)

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      summaries for band data within any given geometry area where the DSWE value is 1
  """
  # process image with the radsat mask
  r = add_rad_mask(image).select("radsat")
  # process image with cfmask
  f = cf_mask(image).select("cfmask")
  # process image with aerosol mask
  a = sr_aerosol(image).select("medHighAero")
  # where the f mask is >= 1 (clouds and cloud shadow), call that 1 (otherwise 0) and rename as clouds.
  clouds = f.gte(1).rename("clouds")
  #apply dswe function
  d = DSWE(image).select("dswe")
  pCount = d.gt(0).rename("dswe_gt0").updateMask(f.eq(0)).updateMask(r.eq(1)).selfMask()
  dswe1 = d.eq(1).rename("dswe1").updateMask(f.eq(0)).updateMask(r.eq(1)).selfMask()
  # band where dswe is 3 and apply all masks
  dswe3 = d.eq(3).rename("dswe3").updateMask(f.eq(0)).updateMask(r.eq(1)).selfMask()
  #calculate hillshade
  h = calc_hill_shades(image, feat.geometry()).select("hillShade")
  #calculate hillshadow
  hs = calc_hill_shadows(image, feat.geometry()).select("hillShadow")
  img_mask = (d.eq(1) # only confident water
          .updateMask(r.eq(1)) # 1 == no saturated pixels
          .updateMask(f.eq(0)) # no snow or clouds
          .updateMask(hs.eq(1)) # only illuminated pixels
          .selfMask())
  pixOut = (image.select(["Aerosol", "Blue", "Green", "Red", "Nir", "Swir1", "Swir2", 
                      "SurfaceTemp", "temp_qa", "ST_ATRAN", "ST_DRAD", "ST_EMIS",
                      "ST_EMSD", "ST_TRAD", "ST_URAD"],
                      ["med_Aerosol", "med_Blue", "med_Green", "med_Red", "med_Nir", "med_Swir1", "med_Swir2", 
                      "med_SurfaceTemp", "med_temp_qa", "med_atran", "med_drad", "med_emis",
                      "med_emsd", "med_trad", "med_urad"])
          .addBands(image.select(["SurfaceTemp", "ST_CDIST"],
                                  ["min_SurfaceTemp", "min_cloud_dist"]))
          .addBands(image.select(["Aerosol", "Blue", "Green", "Red", 
                                  "Nir", "Swir1", "Swir2", "SurfaceTemp"],
                                ["sd_Aerosol", "sd_Blue", "sd_Green", "sd_Red", 
                                "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"]))
          .addBands(image.select(["Aerosol", "Blue", "Green", "Red", "Nir", 
                                  "Swir1", "Swir2", 
                                  "SurfaceTemp"],
                                ["mean_Aerosol", "mean_Blue", "mean_Green", "mean_Red", "mean_Nir", 
                                "mean_Swir1", "mean_Swir2", 
                                "mean_SurfaceTemp"]))
          .addBands(image.select(["SurfaceTemp"]))
          .updateMask(img_mask.eq(1))
          # add these bands back in to create summary statistics without the influence of the DSWE masks:
          .addBands(pCount) 
          .addBands(dswe1)
          .addBands(dswe3)
          .addBands(a)
          .addBands(clouds) 
          .addBands(hs)
          .addBands(h)
          ) 
  combinedReducer = (ee.Reducer.median().unweighted().forEachBand(pixOut.select(["med_Aerosol", "med_Blue", "med_Green", "med_Red", 
            "med_Nir", "med_Swir1", "med_Swir2", "med_SurfaceTemp", 
            "med_temp_qa","med_atran", "med_drad", "med_emis",
            "med_emsd", "med_trad", "med_urad"]))
    .combine(ee.Reducer.min().unweighted().forEachBand(pixOut.select(["min_SurfaceTemp", "min_cloud_dist"])), sharedInputs = False)
    .combine(ee.Reducer.stdDev().unweighted().forEachBand(pixOut.select(["sd_Aerosol", "sd_Blue", "sd_Green", "sd_Red", "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["mean_Aerosol", "mean_Blue", "mean_Green", "mean_Red", 
              "mean_Nir", "mean_Swir1", "mean_Swir2", "mean_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.kurtosis().unweighted().forEachBand(pixOut.select(["SurfaceTemp"])), outputPrefix = "kurt_", sharedInputs = False)
    .combine(ee.Reducer.count().unweighted().forEachBand(pixOut.select(["dswe_gt0", "dswe1", "dswe3", "medHighAero"])), outputPrefix = "pCount_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["clouds", "hillShadow"])), outputPrefix = "prop_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["hillShade"])), outputPrefix = "mean_", sharedInputs = False)
    )
  # apply combinedReducer to the image collection, mapping over each feature
  lsout = (pixOut.reduceRegions(feat, combinedReducer, 30))
  out = lsout.map(remove_geo)
  return out

def ref_pull_89_DSWE3(image):
  """ This function applies all functions to the Landsat 8 and 9 ee.ImageCollection, extracting
  summary statistics for each geometry area where the DSWE value is 3 (high confidence vegetated
  pixels)

  Args:
      image: ee.Image of an ee.ImageCollection

  Returns:
      summaries for band data within any given geometry area where the DSWE value is 3
  """
  # process image with the radsat mask
  r = add_rad_mask(image).select("radsat")
  # process image with cfmask
  f = cf_mask(image).select("cfmask")
  # process image with aerosol mask
  a = sr_aerosol(image).select("medHighAero")
  # where the f mask is >= 1 (clouds and cloud shadow), call that 1 (otherwise 0) and rename as clouds.
  clouds = f.gte(1).rename("clouds")
  #apply dswe function
  d = DSWE(image).select("dswe")
  pCount = d.gt(0).rename("dswe_gt0").updateMask(f.eq(0)).updateMask(r.eq(1)).selfMask()
  dswe1 = d.eq(1).rename("dswe1").updateMask(f.eq(0)).updateMask(r.eq(1)).selfMask()
  # band where dswe is 3 and apply all masks
  dswe3 = d.eq(3).rename("dswe3").updateMask(f.eq(0)).updateMask(r.eq(1)).selfMask()
  #calculate hillshade
  h = calc_hill_shades(image, feat.geometry()).select("hillShade")
  #calculate hillshadow
  hs = calc_hill_shadows(image, feat.geometry()).select("hillShadow")
  img_mask = (d.eq(3) # only vegetated water
          .updateMask(r.eq(1)) #1 == no saturated pixels
          .updateMask(f.eq(0)) #no snow or clouds
          .updateMask(hs.eq(1)) # only illuminated pixels
          .selfMask())
  pixOut = (image.select(["Aerosol", "Blue", "Green", "Red", "Nir", "Swir1", "Swir2", 
                      "SurfaceTemp", "temp_qa", "ST_ATRAN", "ST_DRAD", "ST_EMIS",
                      "ST_EMSD", "ST_TRAD", "ST_URAD"],
                      ["med_Aerosol", "med_Blue", "med_Green", "med_Red", "med_Nir", "med_Swir1", "med_Swir2", 
                      "med_SurfaceTemp", "med_temp_qa", "med_atran", "med_drad", "med_emis",
                      "med_emsd", "med_trad", "med_urad"])
          .addBands(image.select(["SurfaceTemp", "ST_CDIST"],
                                  ["min_SurfaceTemp", "min_cloud_dist"]))
          .addBands(image.select(["Aerosol", "Blue", "Green", "Red", 
                                  "Nir", "Swir1", "Swir2", "SurfaceTemp"],
                                ["sd_Aerosol", "sd_Blue", "sd_Green", "sd_Red", 
                                "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"]))
          .addBands(image.select(["Aerosol", "Blue", "Green", "Red", "Nir", 
                                  "Swir1", "Swir2", 
                                  "SurfaceTemp"],
                                ["mean_Aerosol", "mean_Blue", "mean_Green", "mean_Red", "mean_Nir", 
                                "mean_Swir1", "mean_Swir2", 
                                "mean_SurfaceTemp"]))
          .addBands(image.select(["SurfaceTemp"]))
          .updateMask(img_mask.eq(1))
          # add these bands back in to create summary statistics without the influence of the DSWE masks:
          .addBands(pCount) 
          .addBands(dswe1)
          .addBands(dswe3)
          .addBands(a)
          .addBands(clouds) 
          .addBands(hs)
          .addBands(h)
          ) 
  combinedReducer = (ee.Reducer.median().unweighted().forEachBand(pixOut.select(["med_Aerosol", "med_Blue", "med_Green", "med_Red", 
            "med_Nir", "med_Swir1", "med_Swir2", "med_SurfaceTemp", 
            "med_temp_qa","med_atran", "med_drad", "med_emis",
            "med_emsd", "med_trad", "med_urad"]))
    .combine(ee.Reducer.min().unweighted().forEachBand(pixOut.select(["min_SurfaceTemp", "min_cloud_dist"])), sharedInputs = False)
    .combine(ee.Reducer.stdDev().unweighted().forEachBand(pixOut.select(["sd_Aerosol", "sd_Blue", "sd_Green", "sd_Red", "sd_Nir", "sd_Swir1", "sd_Swir2", "sd_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["mean_Aerosol", "mean_Blue", "mean_Green", "mean_Red", 
              "mean_Nir", "mean_Swir1", "mean_Swir2", "mean_SurfaceTemp"])), sharedInputs = False)
    .combine(ee.Reducer.kurtosis().unweighted().forEachBand(pixOut.select(["SurfaceTemp"])), outputPrefix = "kurt_", sharedInputs = False)
    .combine(ee.Reducer.count().unweighted().forEachBand(pixOut.select(["dswe_gt0", "dswe1", "dswe3", "medHighAero"])), outputPrefix = "pCount_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["clouds", "hillShadow"])), outputPrefix = "prop_", sharedInputs = False)
    .combine(ee.Reducer.mean().unweighted().forEachBand(pixOut.select(["hillShade"])), outputPrefix = "mean_", sharedInputs = False)
    )
  # apply combinedReducer to the image collection, mapping over each feature
  lsout = (pixOut.reduceRegions(feat, combinedReducer, 30))
  out = lsout.map(remove_geo)
  return out


def maximum_no_of_tasks(MaxNActive, waitingPeriod):
  """ Function to limit the number of tasks sent to Earth Engine at one time to avoid time out errors
  
  Args:
      MaxNActive: maximum number of tasks that can be active in Earth Engine at one time
      waitingPeriod: time to wait between checking if tasks are completed, in seconds
      
  Returns:
      None.
  """
  ##maintain a maximum number of active tasks
  ## initialize submitting jobs
  ts = list(ee.batch.Task.list())
  NActive = 0
  for task in ts:
     if ("RUNNING" in str(task) or "READY" in str(task)):
         NActive += 1
  ## wait if the number of current active tasks reach the maximum number
  ## defined in MaxNActive
  while (NActive >= MaxNActive):
    time.sleep(waitingPeriod) # if reach or over maximum no. of active tasks, wait for 2min and check again
    ts = list(ee.batch.Task.list())
    NActive = 0
    for task in ts:
      if ("RUNNING" in str(task) or "READY" in str(task)):
        NActive += 1
  return()

